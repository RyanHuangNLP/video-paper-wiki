"""Native pypdf extraction to page-anchored Markdown. No Docling, no blob copy."""

from __future__ import annotations

import fcntl
import hashlib
import importlib.metadata
import json
import os
import re
import secrets
import unicodedata
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, PdfReadError, PdfStreamError

from video_paper_wiki_research.contracts import MANUAL_PDF_INVALID, PARSER_NO_TEXT, ResearchError
from video_paper_wiki_research.light_index import _load_paper, _locate_pages

SCHEMA = "video-paper-wiki.light-paper.v1"
ENGINE = "pypdf-native-text"
EMPTY_PAGE_WARNING = "page {page} has no native text"
NO_TEXT_MESSAGE = "No native text found. This lightweight path does not run OCR or download models."
DISCLAIMER = (
    "按 PDF 文件页码保留原生文本。未运行 OCR、版面模型或表格重建；"
    "图中内容可能缺失，多栏、公式和表格的文字顺序需对照原 PDF。"
)
TRANSACTION_SCHEMA = "video-paper-wiki.light-pdf-transaction.v1"
TRANSACTIONS_DIR = ".light-transactions"
STAGING_DIRNAME = "staging"
PAYLOAD_NAMES = ("source.md", "source.json")
LIGHT_WORKSPACE_BUSY = "LIGHT_WORKSPACE_BUSY"
LIGHT_PAPER_CONFLICT = "LIGHT_PAPER_CONFLICT"
SOURCE_INVALID = "SOURCE_INVALID"
WORKSPACE_INVALID = "WORKSPACE_INVALID"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
INJECT_POINTS = (
    "after_lock",
    "after_staging_create",
    "after_md_write",
    "after_json_write",
    "before_publish",
    "after_publish",
)

_inject_hooks: dict[str, Callable[[str], None]] = {}


def _fail(code: str, message: str, details: dict[str, Any] | None = None) -> None:
    raise ResearchError(code, message, details)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _normalize_page_text(raw: str | None) -> str:
    text = unicodedata.normalize("NFC", raw or "")
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _read_pdf(pdf_path: Path) -> tuple[Path, bytes, str]:
    source = Path(pdf_path)
    if not source.is_file() or source.is_symlink():
        _fail(MANUAL_PDF_INVALID, "PDF path must be a regular file", {"path": str(source)})
    try:
        data = source.read_bytes()
    except OSError as exc:
        _fail(MANUAL_PDF_INVALID, "PDF is not readable", {"path": str(source)})
        raise AssertionError("unreachable") from exc
    if not data.startswith(b"%PDF-"):
        _fail(MANUAL_PDF_INVALID, "PDF must start with %PDF-", {"path": str(source)})
    digest = _sha256_bytes(data)
    return source.resolve(), data, digest


def _page_texts(data: bytes) -> list[str]:
    try:
        reader = PdfReader(BytesIO(data))
    except (PdfReadError, PdfStreamError, OSError, ValueError) as exc:
        _fail(MANUAL_PDF_INVALID, "PDF is not parseable")
        raise AssertionError("unreachable") from exc
    if bool(getattr(reader, "is_encrypted", False)):
        _fail(MANUAL_PDF_INVALID, "Encrypted PDF: provide an unlocked source file")
    try:
        pages = list(reader.pages)
    except FileNotDecryptedError as exc:
        _fail(MANUAL_PDF_INVALID, "Encrypted PDF: provide an unlocked source file")
        raise AssertionError("unreachable") from exc
    except Exception as exc:
        _fail(MANUAL_PDF_INVALID, "PDF is not parseable")
        raise AssertionError("unreachable") from exc
    if not pages:
        _fail(MANUAL_PDF_INVALID, "PDF has no pages")
    return [_normalize_page_text(page.extract_text() or "") for page in pages]


def _build_markdown(title: str, source: Path, digest: str, bodies: list[str]) -> tuple[str, list[dict[str, Any]], list[str]]:
    header = (
        f"# {title}\n"
        f"\n"
        f"原始 PDF：[本机文件](<{source}>)\n"
        f"\n"
        f"SHA-256：`{digest}`\n"
        f"\n"
        f"{DISCLAIMER}\n"
        f"\n"
    )
    markdown = header
    pages: list[dict[str, Any]] = []
    warnings: list[str] = []
    for number, body in enumerate(bodies, start=1):
        markdown += f'<a id="page-{number}"></a>\n\n## PDF 第 {number} 页\n\n'
        start = len(markdown)
        markdown += body
        end = len(markdown)
        markdown += "\n"
        if start == end:
            warnings.append(EMPTY_PAGE_WARNING.format(page=number))
        slice_text = markdown[start:end]
        pages.append(
            {
                "page": number,
                "anchor": f"page-{number}",
                "text_start": start,
                "text_end": end,
                "text_sha256": _sha256_text(slice_text),
            }
        )
    return markdown, pages, warnings


def set_inject_hook(point: str | None, hook: Callable[[str], None] | None = None) -> None:
    """Test-only seam. Production callers must not set this."""
    _inject_hooks.clear()
    if point is not None and hook is not None:
        if point not in INJECT_POINTS:
            raise ValueError(f"unknown inject point: {point}")
        _inject_hooks[point] = hook


def _run_inject(point: str) -> None:
    hook = _inject_hooks.get(point)
    if hook is not None:
        hook(point)
    env_point = os.environ.get("VPWIKI_LIGHT_PDF_INJECT")
    if env_point != point:
        return
    ready = os.environ.get("VPWIKI_LIGHT_PDF_INJECT_READY")
    wait = os.environ.get("VPWIKI_LIGHT_PDF_INJECT_WAIT")
    action = os.environ.get("VPWIKI_LIGHT_PDF_INJECT_ACTION", "exit")
    if ready:
        ready_path = Path(ready)
        with open(ready_path, "w", encoding="utf-8") as handle:
            handle.write(point + "\n")
            handle.flush()
    if wait:
        with open(wait, "r", encoding="utf-8") as handle:
            handle.read()
    if action == "continue":
        return
    if action == "raise":
        raise RuntimeError(f"injected failure at {point}")
    os._exit(77)


def _closed(status: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "status": status, "message": message}
    payload.update(extra)
    return payload


def _success(
    *,
    paper_id: str,
    metadata_path: Path,
    markdown_path: Path,
    page_count: int,
    warnings: list[str],
    disposition: str,
    message: str,
) -> dict[str, Any]:
    return {
        "ok": True,
        "status": "OK",
        "message": message,
        "paper_id": paper_id,
        "metadata_path": str(metadata_path.resolve()),
        "markdown_path": str(markdown_path.resolve()),
        "page_count": page_count,
        "warnings": list(warnings),
        "disposition": disposition,
    }


def _prepare_workspace(workspace_root: Path) -> Path:
    """Validate/create only the workspace root. Papers and transactions wait for the lock."""
    root = Path(workspace_root)
    if root.is_symlink() or (root.exists() and not root.is_dir()):
        _fail(WORKSPACE_INVALID, "workspace_root must be a regular directory", {"path": str(root)})
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _fail(WORKSPACE_INVALID, "workspace_root is not writable", {"path": str(root)})
        raise AssertionError("unreachable") from exc
    if root.is_symlink() or not root.is_dir():
        _fail(WORKSPACE_INVALID, "workspace_root must be a regular directory", {"path": str(root)})
    return root.resolve()


def _ensure_papers_dir(workspace: Path) -> Path:
    papers = workspace / "papers"
    if os.path.lexists(papers) and (papers.is_symlink() or not papers.is_dir()):
        _fail(WORKSPACE_INVALID, "papers/ must be a regular directory", {"path": str(papers)})
    papers.mkdir(exist_ok=True)
    if papers.is_symlink() or not papers.is_dir():
        _fail(WORKSPACE_INVALID, "papers/ must be a regular directory", {"path": str(papers)})
    return papers


def _ensure_regular_dir(path: Path, *, create: bool, label: str) -> None:
    if path.is_symlink():
        _fail(WORKSPACE_INVALID, f"{label} must not be a symlink", {"path": str(path)})
    if os.path.lexists(path) and not path.is_dir():
        _fail(WORKSPACE_INVALID, f"{label} must be a regular directory", {"path": str(path)})
    if not os.path.lexists(path):
        if not create:
            _fail(WORKSPACE_INVALID, f"{label} is missing", {"path": str(path)})
        try:
            path.mkdir(exist_ok=False)
        except OSError as exc:
            _fail(WORKSPACE_INVALID, f"{label} is not writable", {"path": str(path)})
            raise AssertionError("unreachable") from exc
    if path.is_symlink() or not path.is_dir():
        _fail(WORKSPACE_INVALID, f"{label} must be a regular directory", {"path": str(path)})


def _ensure_transaction_dir(workspace: Path) -> Path:
    tx_dir = workspace / TRANSACTIONS_DIR
    _ensure_regular_dir(tx_dir, create=True, label=".light-transactions")
    return tx_dir


class _AdvisoryLock:
    def __init__(self, fd: int) -> None:
        self.fd = fd

    def release(self) -> None:
        if self.fd is None:
            return
        try:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        finally:
            os.close(self.fd)
            self.fd = None  # type: ignore[assignment]


def lock_path_for(workspace: Path, digest: str) -> Path:
    return workspace / TRANSACTIONS_DIR / f"{digest}.lock"


def _try_lock(workspace: Path, digest: str) -> _AdvisoryLock | None:
    _ensure_transaction_dir(workspace)
    path = lock_path_for(workspace, digest)
    if path.is_symlink() or (os.path.lexists(path) and not path.is_file()):
        _fail(WORKSPACE_INVALID, "lock path must be a regular file", {"path": str(path)})
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o644)
    except OSError as exc:
        _fail(WORKSPACE_INVALID, "lock path is not a writable regular file", {"path": str(path)})
        raise AssertionError("unreachable") from exc
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    except OSError:
        os.close(fd)
        return None
    return _AdvisoryLock(fd)


def lock_is_held(lock_path: Path) -> bool:
    """True only when another process currently holds the advisory lock."""
    if lock_path.is_symlink() or not lock_path.is_file():
        return False
    try:
        fd = os.open(lock_path, os.O_RDWR)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
    return False


def _entry_kind(path: Path) -> str:
    if path.is_symlink():
        return "symlink"
    if path.is_file():
        return "file"
    if path.is_dir():
        return "dir"
    return "other"


def _list_names(directory: Path) -> list[str]:
    try:
        return sorted(item.name for item in directory.iterdir())
    except OSError:
        return []


def _decode_pair(directory: Path) -> tuple[str, str] | None:
    try:
        markdown = (directory / "source.md").read_bytes().decode("utf-8")
        raw_json = (directory / "source.json").read_bytes().decode("utf-8")
    except (OSError, UnicodeError):
        return None
    return markdown, raw_json


def _validate_payload(directory: Path, digest: str) -> dict[str, Any]:
    """Validate a two-file payload against digest. Directory name may be a staging token."""
    if _entry_kind(directory) != "dir":
        return {"kind": "unsafe", "reason": "payload path is not a regular directory"}
    names = _list_names(directory)
    kinds = {name: _entry_kind(directory / name) for name in names}
    if any(name not in PAYLOAD_NAMES for name in names) or any(kinds[name] != "file" for name in names):
        return {"kind": "unknown", "reason": "owned payload set is not exactly two regular files", "names": names}
    if any(name not in kinds for name in PAYLOAD_NAMES):
        return {"kind": "partial", "reason": "owned payload is incomplete", "names": names}
    decoded = _decode_pair(directory)
    if decoded is None:
        return {"kind": "invalid", "reason": "paper files are not valid UTF-8", "code": SOURCE_INVALID, "names": names}
    markdown, raw_json = decoded
    try:
        meta = json.loads(raw_json)
    except json.JSONDecodeError:
        return {"kind": "invalid", "reason": "source.json is not valid JSON", "code": SOURCE_INVALID, "names": names}
    if type(meta) is not dict:
        return {"kind": "invalid", "reason": "source.json root must be an object", "code": SOURCE_INVALID, "names": names}
    if meta.get("schema") != SCHEMA or meta.get("paper_id") != f"sha256:{digest}":
        return {"kind": "identity", "reason": "source.json paper identity differs", "code": SOURCE_INVALID, "names": names}
    source = meta.get("source") if type(meta.get("source")) is dict else {}
    if source.get("sha256") != digest:
        return {"kind": "identity", "reason": "source.json identity does not match the PDF digest", "code": SOURCE_INVALID, "names": names}
    document = meta.get("document")
    if type(document) is not dict or document.get("path") != f"papers/{digest}/source.md":
        return {"kind": "invalid", "reason": "source.md digest or path differs from source.json", "code": SOURCE_INVALID, "names": names}
    if type(meta.get("page_count")) is not int:
        return {"kind": "invalid", "reason": "source.json pages are invalid", "code": SOURCE_INVALID, "names": names}
    try:
        _locate_pages(markdown, page_count=meta["page_count"])
    except ResearchError as exc:
        return {"kind": "invalid", "reason": exc.message, "code": exc.code or SOURCE_INVALID, "names": names}
    return {"kind": "complete", "names": names, "metadata": meta}


def _inspect_regular_paper_tree(directory: Path) -> dict[str, Any] | None:
    """Inspect descendants without following symlinks. None means only regular files/dirs."""
    pending = [directory]
    while pending:
        current = pending.pop()
        if current.is_symlink() or not current.is_dir():
            return {"kind": "unsafe", "reason": "paper path is not a regular directory"}
        try:
            entries = list(os.scandir(current))
        except OSError:
            return {"kind": "unsafe", "reason": "paper tree could not be inspected"}
        for entry in entries:
            try:
                rel = Path(entry.path).relative_to(directory).as_posix()
                if entry.is_symlink():
                    return {"kind": "unsafe", "reason": f"unexpected symlink {rel}"}
                if entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
                    continue
                if entry.is_file(follow_symlinks=False):
                    st = entry.stat(follow_symlinks=False)
                    if st.st_nlink != 1:
                        return {"kind": "unsafe", "reason": f"unexpected hardlink {rel}"}
                    continue
            except OSError:
                return {"kind": "unsafe", "reason": "paper tree could not be inspected"}
            return {"kind": "unsafe", "reason": f"unexpected nonregular {rel}"}
    return None


def classify_paper_dir(directory: Path, digest: str) -> dict[str, Any]:
    """Classify papers/<digest> without deleting anything."""
    if not os.path.lexists(directory):
        return {"kind": "absent"}
    kind = _entry_kind(directory)
    if kind != "dir":
        return {"kind": "unsafe", "reason": "paper path is not a regular directory"}
    try:
        names = sorted(item.name for item in directory.iterdir())
    except OSError:
        return {"kind": "unsafe", "reason": "paper directory could not be inspected"}
    seen: dict[str, str] = {}
    extras: list[str] = []
    for name in names:
        child = directory / name
        seen[name] = _entry_kind(child)
        if name in PAYLOAD_NAMES:
            continue
        extras.append(name)
    for required in PAYLOAD_NAMES:
        if required not in seen:
            return {"kind": "partial", "reason": f"missing {required}", "names": names}
        if seen[required] != "file":
            return {"kind": "unsafe", "reason": f"{required} is not a regular file", "names": names}
    tree_error = _inspect_regular_paper_tree(directory)
    if tree_error is not None:
        tree_error["names"] = names
        return tree_error
    decoded = _decode_pair(directory)
    if decoded is None:
        return {"kind": "invalid", "reason": "paper files are not valid UTF-8", "code": SOURCE_INVALID, "names": names}
    try:
        loaded = _load_paper(directory)
    except ResearchError as exc:
        return {"kind": "invalid", "reason": exc.message, "code": exc.code, "names": names}
    except (UnicodeError, json.JSONDecodeError):
        return {"kind": "invalid", "reason": "paper files are not valid UTF-8 JSON/Markdown", "code": SOURCE_INVALID, "names": names}
    source = loaded["metadata"].get("source")
    source_sha = source.get("sha256") if type(source) is dict else None
    if type(source_sha) is not str or source_sha != digest or directory.name != digest:
        return {
            "kind": "identity",
            "reason": "source.json identity does not match the PDF digest",
            "names": names,
            "loaded": loaded,
        }
    return {"kind": "complete", "names": names, "loaded": loaded, "extras": extras}


def _marker_payload(digest: str, token: str) -> dict[str, Any]:
    staging_rel = f"{TRANSACTIONS_DIR}/{STAGING_DIRNAME}/{digest}--{token}"
    return {
        "schema": TRANSACTION_SCHEMA,
        "digest": digest,
        "token": token,
        "owned_relative_paths": [f"{staging_rel}/{name}" for name in PAYLOAD_NAMES],
    }


def _marker_path(workspace: Path, digest: str, token: str) -> Path:
    return workspace / TRANSACTIONS_DIR / f"{digest}--{token}.owner.json"


def _staging_dir(workspace: Path, digest: str, token: str) -> Path:
    return workspace / TRANSACTIONS_DIR / STAGING_DIRNAME / f"{digest}--{token}"


def _read_marker(path: Path) -> dict[str, Any] | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if type(value) is not dict or value.get("schema") != TRANSACTION_SCHEMA:
        return None
    digest = value.get("digest")
    token = value.get("token")
    owned = value.get("owned_relative_paths")
    if type(digest) is not str or not _HEX64.fullmatch(digest):
        return None
    if type(token) is not str or not token:
        return None
    if type(owned) is not list or [item for item in owned if type(item) is not str] != []:
        return None
    expected = _marker_payload(digest, token)
    if list(owned) != expected["owned_relative_paths"]:
        return None
    return expected


def iter_markers(workspace: Path, digest: str | None = None) -> list[tuple[Path, dict[str, Any]]]:
    tx_dir = workspace / TRANSACTIONS_DIR
    if tx_dir.is_symlink() or not tx_dir.is_dir():
        return []
    found: list[tuple[Path, dict[str, Any]]] = []
    for item in sorted(tx_dir.iterdir(), key=lambda path: path.name):
        if not item.name.endswith(".owner.json"):
            continue
        marker = _read_marker(item)
        if marker is None:
            continue
        if digest is not None and marker["digest"] != digest:
            continue
        found.append((item, marker))
    return found


def _unlink_if_regular(path: Path) -> bool:
    if not os.path.lexists(path):
        return True
    if path.is_symlink() or not path.is_file():
        return False
    try:
        path.unlink()
    except OSError:
        return False
    return True


def _remove_empty_dir(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        return
    try:
        if _list_names(path):
            return
        path.rmdir()
    except OSError:
        return


def _staging_status(workspace: Path, marker: dict[str, Any]) -> str:
    staging = _staging_dir(workspace, marker["digest"], marker["token"])
    if not os.path.lexists(staging):
        return "missing"
    if _entry_kind(staging) != "dir":
        return "unknown"
    names = _list_names(staging)
    kinds = {name: _entry_kind(staging / name) for name in names}
    extras = [name for name in names if name not in PAYLOAD_NAMES]
    if extras or any(kinds[name] != "file" for name in names):
        return "unknown"
    present = [name for name in PAYLOAD_NAMES if name in kinds]
    if len(present) == len(PAYLOAD_NAMES):
        return "complete"
    return "incomplete"


def _cleanup_owned(workspace: Path, digest: str) -> None:
    for marker_path, marker in iter_markers(workspace, digest):
        status = _staging_status(workspace, marker)
        if status == "unknown":
            continue
        staging = _staging_dir(workspace, digest, marker["token"])
        if status in {"complete", "incomplete", "missing"}:
            for relative in marker["owned_relative_paths"]:
                if not _unlink_if_regular(workspace / relative):
                    break
            else:
                _remove_empty_dir(staging)
                parent = staging.parent
                _remove_empty_dir(parent)
                if marker_path.is_symlink() or not marker_path.is_file():
                    continue
                marker_path.unlink()


def _warnings_from_meta(meta: dict[str, Any]) -> list[str]:
    warnings = meta.get("warnings")
    if type(warnings) is not list:
        return []
    return [item for item in warnings if type(item) is str]


def _reuse_result(loaded: dict[str, Any], *, paper_dir: Path) -> dict[str, Any]:
    meta = loaded["metadata"]
    return _success(
        paper_id=loaded["paper_id"],
        metadata_path=paper_dir / "source.json",
        markdown_path=paper_dir / "source.md",
        page_count=int(loaded["page_count"]),
        warnings=_warnings_from_meta(meta),
        disposition="reused",
        message="reused existing paper without rewriting notes",
    )


def _title_conflict(loaded: dict[str, Any], title: str | None) -> bool:
    if not (isinstance(title, str) and title.strip()):
        return False
    existing = loaded["metadata"].get("title")
    if type(existing) is not str:
        return False
    return title.strip() != existing


def _write_marker(path: Path, marker: dict[str, Any]) -> None:
    _ensure_regular_dir(path.parent, create=True, label=".light-transactions")
    if path.is_symlink() or (os.path.lexists(path) and not path.is_file()):
        _fail(WORKSPACE_INVALID, "transaction marker must be a regular file", {"path": str(path)})
    encoded = json.dumps(marker, ensure_ascii=False, indent=2) + "\n"
    path.write_text(encoded, encoding="utf-8")


def _publish_new(
    *,
    workspace: Path,
    digest: str,
    markdown: str,
    metadata: dict[str, Any],
) -> dict[str, Any] | None:
    token = secrets.token_hex(16)
    marker = _marker_payload(digest, token)
    marker_path = _marker_path(workspace, digest, token)
    staging = _staging_dir(workspace, digest, token)
    dest = workspace / "papers" / digest
    tx_dir = _ensure_transaction_dir(workspace)
    _ensure_regular_dir(tx_dir / STAGING_DIRNAME, create=True, label="transaction staging")
    if staging.is_symlink() or os.path.lexists(staging):
        _fail(WORKSPACE_INVALID, "staging path must be a new regular directory", {"path": str(staging)})
    _write_marker(marker_path, marker)
    staging.mkdir(exist_ok=False)
    _run_inject("after_staging_create")
    try:
        (staging / "source.md").write_text(markdown, encoding="utf-8")
        _run_inject("after_md_write")
        (staging / "source.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        _run_inject("after_json_write")
        _run_inject("before_publish")
        if os.path.lexists(dest):
            return None
        os.rename(staging, dest)
        _run_inject("after_publish")
        if marker_path.is_file() and not marker_path.is_symlink():
            marker_path.unlink()
        _remove_empty_dir(workspace / TRANSACTIONS_DIR / STAGING_DIRNAME)
        return _success(
            paper_id=metadata["paper_id"],
            metadata_path=dest / "source.json",
            markdown_path=dest / "source.md",
            page_count=int(metadata["page_count"]),
            warnings=_warnings_from_meta(metadata),
            disposition="created",
            message="published a complete paper directory",
        )
    except BaseException:
        raise


def _recover_owned(workspace: Path, digest: str) -> dict[str, Any] | None:
    dest = workspace / "papers" / digest
    for marker_path, marker in iter_markers(workspace, digest):
        status = _staging_status(workspace, marker)
        staging = _staging_dir(workspace, digest, marker["token"])
        if status == "complete" and not os.path.lexists(dest):
            payload = _validate_payload(staging, digest)
            if payload["kind"] != "complete":
                return _closed(
                    SOURCE_INVALID,
                    payload.get("reason") or "owned staging is not a valid paper pair",
                    paper_id=f"sha256:{digest}",
                )
            os.rename(staging, dest)
            if marker_path.is_file() and not marker_path.is_symlink():
                marker_path.unlink()
            _remove_empty_dir(workspace / TRANSACTIONS_DIR / STAGING_DIRNAME)
            classified = classify_paper_dir(dest, digest)
            if classified["kind"] != "complete":
                return _closed(
                    SOURCE_INVALID,
                    "recovered directory is not a valid paper pair",
                    paper_id=f"sha256:{digest}",
                )
            loaded = classified["loaded"]
            return _success(
                paper_id=loaded["paper_id"],
                metadata_path=dest / "source.json",
                markdown_path=dest / "source.md",
                page_count=int(loaded["page_count"]),
                warnings=_warnings_from_meta(loaded["metadata"]),
                disposition="recovered",
                message="recovered a complete owned staging directory",
            )
        if status in {"incomplete", "missing"}:
            _cleanup_owned(workspace, digest)
    return None


def extract_pdf(pdf_path: Path, workspace_root: Path, *, title: str | None = None) -> dict[str, Any]:
    """Extract native PDF text into workspace/papers/<sha256>/{source.md,source.json}."""

    source, data, digest = _read_pdf(Path(pdf_path))
    bodies = _page_texts(data)
    if not any(bodies):
        _fail(PARSER_NO_TEXT, NO_TEXT_MESSAGE, {"path": str(source)})
    display_title = title.strip() if isinstance(title, str) and title.strip() else source.stem
    markdown, page_records, warnings = _build_markdown(display_title, source, digest, bodies)
    if _sha256_bytes(source.read_bytes()) != digest:
        _fail(MANUAL_PDF_INVALID, "Source PDF changed during extraction", {"path": str(source)})

    workspace = _prepare_workspace(Path(workspace_root))
    from video_paper_wiki_research.light_library_state import try_workspace_lock

    workspace_lock = try_workspace_lock(workspace)
    if workspace_lock is None:
        return _closed(
            LIGHT_WORKSPACE_BUSY,
            "another cooperating operation currently owns this workspace",
            paper_id=f"sha256:{digest}",
        )
    try:
        _ensure_papers_dir(workspace)
        lock = _try_lock(workspace, digest)
        if lock is None:
            return _closed(
                LIGHT_WORKSPACE_BUSY,
                "another cooperating add currently owns this paper digest",
                paper_id=f"sha256:{digest}",
            )
        try:
            return _extract_locked(
                workspace=workspace,
                source=source,
                data=data,
                digest=digest,
                display_title=display_title,
                markdown=markdown,
                page_records=page_records,
                warnings=warnings,
                title=title,
                page_count=len(bodies),
            )
        finally:
            lock.release()
    finally:
        workspace_lock.release()


def _extract_locked(
    *,
    workspace: Path,
    source: Path,
    data: bytes,
    digest: str,
    display_title: str,
    markdown: str,
    page_records: list[dict[str, Any]],
    warnings: list[str],
    title: str | None,
    page_count: int,
) -> dict[str, Any]:
    _run_inject("after_lock")
    paper_dir = workspace / "papers" / digest
    classified = classify_paper_dir(paper_dir, digest)
    kind = classified["kind"]
    if kind == "complete":
        loaded = classified["loaded"]
        if _title_conflict(loaded, title):
            return _closed(
                LIGHT_PAPER_CONFLICT,
                "explicit title conflicts with the existing paper title",
                paper_id=loaded["paper_id"],
            )
        _cleanup_owned(workspace, digest)
        return _reuse_result(loaded, paper_dir=paper_dir)
    if kind != "absent":
        return _closed(
            SOURCE_INVALID,
            classified.get("reason") or "existing paper directory cannot be reused or replaced",
            paper_id=f"sha256:{digest}",
        )
    recovered = _recover_owned(workspace, digest)
    if recovered is not None:
        return recovered
    markdown_sha = _sha256_bytes(markdown.encode("utf-8"))
    metadata = {
        "schema": SCHEMA,
        "paper_id": f"sha256:{digest}",
        "title": display_title,
        "source": {
            "path": str(source),
            "sha256": digest,
            "size_bytes": len(data),
        },
        "parser": {
            "engine": ENGINE,
            "version": importlib.metadata.version("pypdf"),
        },
        "page_count": page_count,
        "document": {"path": f"papers/{digest}/source.md", "sha256": markdown_sha},
        "pages": page_records,
        "warnings": warnings,
    }
    published = _publish_new(workspace=workspace, digest=digest, markdown=markdown, metadata=metadata)
    if published is not None:
        return published
    classified = classify_paper_dir(paper_dir, digest)
    if classified["kind"] == "complete":
        loaded = classified["loaded"]
        if _title_conflict(loaded, title):
            return _closed(
                LIGHT_PAPER_CONFLICT,
                "explicit title conflicts with the existing paper title",
                paper_id=loaded["paper_id"],
            )
        return _reuse_result(loaded, paper_dir=paper_dir)
    return _closed(
        SOURCE_INVALID,
        "paper directory appeared during publish and is not a reusable pair",
        paper_id=f"sha256:{digest}",
    )


def classify_transaction_tree(workspace: Path) -> dict[str, Any]:
    """Classify `.light-transactions` for backup: exclude only unlocked locks and empty staging."""
    tx_dir = workspace / TRANSACTIONS_DIR
    if not os.path.lexists(tx_dir):
        return {"kind": "absent", "exclude": [], "message": None}
    if tx_dir.is_symlink() or not tx_dir.is_dir():
        return {"kind": "unsafe", "exclude": [], "message": ".light-transactions is not a regular directory"}
    exclude: list[str] = []
    recognized_markers = {path.name: marker for path, marker in iter_markers(workspace)}
    recognized_staging: set[str] = set()
    for marker in recognized_markers.values():
        recognized_staging.add(f"{marker['digest']}--{marker['token']}")
        status = _staging_status(workspace, marker)
        if status != "missing":
            return {
                "kind": "pending",
                "exclude": [],
                "message": "pending recognized PDF publication staging must be recovered first",
            }
        lock = lock_path_for(workspace, marker["digest"])
        if lock_is_held(lock):
            return {
                "kind": "pending",
                "exclude": [],
                "message": f"active paper lock for digest {marker['digest']}",
            }
    for item in sorted(tx_dir.iterdir(), key=lambda path: path.name):
        relative = f"{TRANSACTIONS_DIR}/{item.name}"
        if item.name.endswith(".lock"):
            digest = item.name[: -len(".lock")]
            if item.is_symlink() or not item.is_file() or not _HEX64.fullmatch(digest):
                return {"kind": "unknown", "exclude": [], "message": f"unrecognized lock entry {relative}"}
            if lock_is_held(item):
                return {"kind": "pending", "exclude": [], "message": f"active paper lock {relative}"}
            exclude.append(relative)
            continue
        if item.name.endswith(".owner.json"):
            if item.name not in recognized_markers:
                return {"kind": "unknown", "exclude": [], "message": f"unrecognized transaction marker {relative}"}
            return {"kind": "pending", "exclude": [], "message": f"pending transaction marker {relative}"}
        if item.name == STAGING_DIRNAME:
            if item.is_symlink() or not item.is_dir():
                return {"kind": "unsafe", "exclude": [], "message": "transaction staging is not a regular directory"}
            children = _list_names(item)
            if children:
                return {"kind": "pending", "exclude": [], "message": "nonempty PDF transaction staging must be recovered first"}
            exclude.append(relative)
            continue
        return {"kind": "unknown", "exclude": [], "message": f"unexpected transaction entry {relative}"}
    return {"kind": "clean", "exclude": exclude, "message": None}
