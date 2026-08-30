"""Local ingest put and run. Copies a local file into the blob store. Zero network."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any, Callable

from video_paper_wiki.blob_store import BlobStore, resolve_blob_root
from video_paper_wiki.commands import draft as draft_commands
from video_paper_wiki.commands import review as review_commands
from video_paper_wiki.envelope import emit_error, emit_success
from video_paper_wiki.parse.draft_document import InvalidPaperId, validate_paper_id
from video_paper_wiki.resources import load_seed_json, resolve_seed_path

_COPY_KEY = "VAULT_PATH".lower()
_SEED_FILE = "engine-mvp.json"
_COMMAND = "ingest.run"


def put(_args: object | None = None) -> int:
    raw = None if _args is None else getattr(_args, "path", None)
    if raw is None or str(raw).strip() == "":
        return emit_error(
            "ingest.put",
            "USAGE",
            "ingest.put requires --path",
        )
    path = Path(str(raw)).expanduser()
    try:
        if not path.is_file():
            return emit_error(
                "ingest.put",
                "BLOB_SOURCE_NOT_FOUND",
                "local source file is missing or unreadable; this command does not download",
                {"path": str(raw)},
            )
        store = BlobStore(resolve_blob_root())
        digest = store.put_from_path(path)
    except OSError as exc:
        return emit_error(
            "ingest.put",
            "BLOB_SOURCE_NOT_FOUND",
            "local source file is missing or unreadable; this command does not download",
            {"path": str(raw), "reason": str(exc)},
        )
    stored = store.path_for(digest)
    return emit_success(
        "ingest.put",
        {
            "sha256": digest,
            "path": stored.as_posix(),
        },
    )


def _invoke(handler: Callable[..., int], ns: object) -> tuple[int, str]:
    buf = StringIO()
    with redirect_stdout(buf):
        code = handler(ns)
    return code, buf.getvalue()


def _replay(captured: str, code: int) -> int:
    sys.stdout.write(captured)
    sys.stdout.flush()
    return code


def _raw(args: object | None, name: str) -> Any:
    if args is None:
        return None
    return getattr(args, name, None)


def _seed_not_found(path: str | None) -> int:
    details: dict[str, Any] = {} if path is None else {"path": path}
    return emit_error(
        _COMMAND,
        "SEED_NOT_FOUND",
        "seed catalog is missing or unreadable; this command does not download",
        details,
    )


def _seed_invalid(path: str, reason: str) -> int:
    return emit_error(
        _COMMAND,
        "SEED_INVALID",
        reason,
        {"path": path},
    )


def _papers_from_payload(
    payload: object, path_label: str
) -> tuple[list[dict[str, Any]] | None, int | None]:
    if not isinstance(payload, dict) or not isinstance(payload.get("papers"), list):
        return None, _seed_invalid(path_label, "seed catalog must be an object with a papers array")
    papers: list[dict[str, Any]] = []
    for item in payload["papers"]:
        if not isinstance(item, dict):
            return None, _seed_invalid(path_label, "seed papers entries must be objects")
        papers.append(item)
    return papers, None


def _load_seed_papers(seed_path: Path | None) -> tuple[list[dict[str, Any]] | None, int | None]:
    if seed_path is not None:
        try:
            if not seed_path.is_file():
                return None, _seed_not_found(seed_path.as_posix())
            text = seed_path.read_text(encoding="utf-8")
        except OSError:
            return None, _seed_not_found(seed_path.as_posix())
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            return None, _seed_invalid(
                seed_path.as_posix(), f"seed is not valid JSON: {exc.msg}"
            )
        return _papers_from_payload(payload, seed_path.as_posix())
    payload = load_seed_json(_SEED_FILE)
    if payload is None:
        return None, _seed_not_found(None)
    return _papers_from_payload(payload, _SEED_FILE)


def _match_pdf(pdf_dir: Path, paper_id: str, arxiv_id: str) -> Path | None:
    if paper_id:
        by_id = pdf_dir / f"{paper_id}.pdf"
        if by_id.is_file():
            return by_id
    if arxiv_id:
        by_arxiv = pdf_dir / f"{arxiv_id}.pdf"
        if by_arxiv.is_file():
            return by_arxiv
    return None


def _success_record(data: dict[str, Any]) -> dict[str, Any]:
    record: dict[str, Any] = {
        "sha256": data["sha256"],
        "paper_id": data["paper_id"],
        "draft_path": data["draft_path"],
        "note_path": data["note_path"],
    }
    if _COPY_KEY in data:
        record[_COPY_KEY] = data[_COPY_KEY]
    return record


def _skip_row(paper_id: str, arxiv_id: str, reason: str) -> dict[str, str]:
    return {"paper_id": paper_id, "arxiv_id": arxiv_id, "reason": reason}


def _inner_reason(captured: str) -> str:
    try:
        payload = json.loads(captured.strip())
        code = payload.get("error", {}).get("code")
        if isinstance(code, str) and code:
            return code
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass
    return "inner ingest.run failed"


def _blob_source_not_found(
    seed_label: str,
    pdf_dir_raw: str,
    skipped: list[dict[str, str]],
) -> int:
    return emit_error(
        _COMMAND,
        "BLOB_SOURCE_NOT_FOUND",
        "local pdf-dir is missing, not a directory, or has no matching pdf; this command does not download",
        {
            "seed": seed_label,
            "pdf_dir": pdf_dir_raw,
            "skipped": skipped,
        },
    )


def _run_pdf_dir(_args: object) -> int:
    pdf_dir_raw = str(_raw(_args, "pdf_dir"))
    notes_root = _raw(_args, "notes_root")
    explicit = _raw(_args, "seed_path")
    if explicit is not None and str(explicit).strip() != "":
        seed_path: Path | None = Path(str(explicit)).expanduser()
    else:
        seed_path = resolve_seed_path(_SEED_FILE)
    seed_papers, err = _load_seed_papers(seed_path)
    if err is not None:
        return err
    assert seed_papers is not None
    seed_label = seed_path.as_posix() if seed_path is not None else _SEED_FILE

    pdf_dir = Path(pdf_dir_raw).expanduser()
    skipped: list[dict[str, str]] = []
    if not pdf_dir.is_dir():
        for paper in seed_papers:
            skipped.append(
                _skip_row(
                    str(paper.get("paper_id", "")),
                    str(paper.get("arxiv_id", "")),
                    "pdf-dir is missing or not a directory",
                )
            )
        return _blob_source_not_found(seed_label, pdf_dir_raw, skipped)

    successes: list[dict[str, Any]] = []
    first_failure: tuple[int, str] | None = None
    for paper in seed_papers:
        paper_id = str(paper.get("paper_id", ""))
        arxiv_id = str(paper.get("arxiv_id", ""))
        matched = _match_pdf(pdf_dir, paper_id, arxiv_id)
        if matched is None:
            skipped.append(_skip_row(paper_id, arxiv_id, "local pdf not found"))
            continue
        code, captured = _invoke(
            run,
            Namespace(path=str(matched), paper_id=paper_id, notes_root=notes_root),
        )
        if code != 0:
            skipped.append(_skip_row(paper_id, arxiv_id, _inner_reason(captured)))
            if first_failure is None:
                first_failure = (code, captured)
            continue
        try:
            payload = json.loads(captured.strip())
            data = payload["data"]
        except (json.JSONDecodeError, KeyError, TypeError):
            skipped.append(_skip_row(paper_id, arxiv_id, "inner ingest.run envelope invalid"))
            if first_failure is None:
                first_failure = (code, captured)
            continue
        successes.append(_success_record(data))

    if successes:
        return emit_success(
            _COMMAND,
            {
                "seed": seed_label,
                "pdf_dir": pdf_dir.as_posix(),
                "papers": successes,
                "skipped": skipped,
            },
        )
    if first_failure is not None:
        return _replay(first_failure[1], first_failure[0])
    return _blob_source_not_found(seed_label, pdf_dir_raw, skipped)


def run(_args: object | None = None) -> int:
    path_raw = _raw(_args, "path")
    pdf_dir_raw = _raw(_args, "pdf_dir")
    seed_raw = _raw(_args, "seed_path")
    notes_root = _raw(_args, "notes_root")
    paper_id_arg = _raw(_args, "paper_id")

    has_path = path_raw is not None
    has_pdf_dir = pdf_dir_raw is not None and str(pdf_dir_raw).strip() != ""
    has_seed = seed_raw is not None and str(seed_raw).strip() != ""

    if has_path and has_pdf_dir:
        return emit_error(
            _COMMAND,
            "USAGE",
            "ingest.run --path and --pdf-dir are mutually exclusive",
        )
    if not has_path and not has_pdf_dir:
        return emit_error(
            _COMMAND,
            "USAGE",
            "ingest.run requires --path or --pdf-dir",
        )
    if has_seed and has_path:
        return emit_error(
            _COMMAND,
            "USAGE",
            "ingest.run --seed requires --pdf-dir",
        )
    if has_pdf_dir:
        return _run_pdf_dir(_args if _args is not None else Namespace())

    if paper_id_arg is not None:
        try:
            validate_paper_id(str(paper_id_arg))
        except InvalidPaperId:
            return emit_error(
                "ingest.run",
                "INVALID_PAPER_ID",
                "paper_id is empty or not a safe path segment",
                {"paper_id": str(paper_id_arg)},
            )

    code, captured = _invoke(put, Namespace(path=path_raw))
    if code != 0:
        return _replay(captured, code)
    put_data = json.loads(captured.strip())["data"]
    sha256 = put_data["sha256"]

    code, captured = _invoke(
        draft_commands.export,
        Namespace(sha256=sha256, paper_id=paper_id_arg),
    )
    if code != 0:
        return _replay(captured, code)
    export_data = json.loads(captured.strip())["data"]
    draft_path = export_data["path"]
    paper_id = export_data["paper_id"]

    code, captured = _invoke(draft_commands.validate, Namespace(path=draft_path))
    if code != 0:
        return _replay(captured, code)

    code, captured = _invoke(
        review_commands.export,
        Namespace(draft=draft_path, notes_root=notes_root),
    )
    if code != 0:
        return _replay(captured, code)
    review_data = json.loads(captured.strip())["data"]

    data: dict[str, Any] = {
        "sha256": sha256,
        "paper_id": paper_id,
        "draft_path": draft_path,
        "note_path": review_data["path"],
    }
    if _COPY_KEY in review_data:
        data[_COPY_KEY] = review_data[_COPY_KEY]
    return emit_success("ingest.run", data)
