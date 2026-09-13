"""Staged Docling export. Tests inject a converter via set_test_converter only."""

from __future__ import annotations

import json
import os
import socket
import sys
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from video_paper_wiki import __version__ as VPWIKI_VERSION
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.identity import pipeline_fingerprint
from video_paper_wiki.secure_io import SOURCE_CHANGED, SecureIOError, read_regular_file
from video_paper_wiki.staging import StagingError, validate_batch_id

from video_paper_wiki_research.contracts import (
    DOCLING_CORE_VERSION,
    DOCLING_VERSION,
    DOCUMENT_JSON_MAX_BYTES,
    DOCUMENT_JSON_MAX_DEPTH,
    PARSER_FAILED,
    PARSER_NETWORK_REFUSED,
    PARSER_NO_TEXT,
    PARSER_OUTPUT_INVALID,
    PARSER_PARTIAL_RESULT,
    PARSER_PROFILE_INVALID,
    PARSER_RUNTIME_INCOMPATIBLE,
    PARSER_RUNTIME_MISSING,
    PARSER_RUN_CONFLICT,
    PARSER_RUN_INCOMPLETE,
    PARSER_SOURCE_UNBOUND,
    PDF_MAX_BYTES,
    PDF_MAX_PAGES,
    ResearchError,
    dump_float_json,
    exact_ref,
    jcs_bytes,
    parse_float_json,
    sha256_bytes,
)
from video_paper_wiki_research.manual_pdf import load_intake
from video_paper_wiki_research.parser_profile import installed_versions, load_profile
from video_paper_wiki_research.storage import (
    RetainedResearchSession,
    require_family_slot,
    session_from_research_path,
    stage_research,
)

Converter = Callable[..., Any]
_TEST_CONVERTER: Converter | None = None
RUN_NAMES = ("document.json", "parser-config.json", "model-manifest.json", "run.json")


def set_test_converter(converter: Converter | None) -> None:
    global _TEST_CONVERTER
    _TEST_CONVERTER = converter


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _offline_env() -> dict[str, str]:
    return {
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "DOCLING_DISABLE_TELEMETRY": "1",
    }


class _OfflineSocket(socket.socket):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        family = args[0] if args else kwargs.get("family", socket.AF_INET)
        if family in {socket.AF_INET, socket.AF_INET6}:
            raise ResearchError(PARSER_NETWORK_REFUSED, "parser execution must not create INET sockets")
        super().__init__(*args, **kwargs)


def _patch_offline() -> tuple[Any, Any, Any, dict[str, str | None]]:
    originals = {
        "socket": socket.socket,
        "create_connection": socket.create_connection,
        "getaddrinfo": socket.getaddrinfo,
    }
    previous_env = {key: os.environ.get(key) for key in _offline_env()}
    for key, value in _offline_env().items():
        os.environ[key] = value

    def _refuse_connect(*_args: Any, **_kwargs: Any) -> Any:
        raise ResearchError(PARSER_NETWORK_REFUSED, "parser execution must not connect")

    def _refuse_dns(*_args: Any, **_kwargs: Any) -> Any:
        raise ResearchError(PARSER_NETWORK_REFUSED, "parser execution must not resolve DNS")

    socket.socket = _OfflineSocket  # type: ignore[misc]
    socket.create_connection = _refuse_connect  # type: ignore[misc]
    socket.getaddrinfo = _refuse_dns  # type: ignore[misc]
    return originals["socket"], originals["create_connection"], originals["getaddrinfo"], previous_env


def _restore_offline(sock: Any, connect: Any, dns: Any, env: dict[str, str | None]) -> None:
    socket.socket = sock
    socket.create_connection = connect
    socket.getaddrinfo = dns
    for key, value in env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _status_success(result: Any) -> bool:
    status = getattr(result, "status", None)
    if status is None:
        return False
    name = getattr(status, "name", None) or str(status)
    return str(name).split(".")[-1].upper() == "SUCCESS"


def _has_nonempty_text(document: dict[str, Any]) -> bool:
    texts = document.get("texts")
    if type(texts) is not list:
        return False
    for node in texts:
        if type(node) is dict and type(node.get("text")) is str and node["text"].strip():
            return True
    return False


def _real_convert(*, pdf_bytes: bytes, name: str, artifacts_path: Path, options: dict[str, Any]) -> Any:
    try:
        from docling.datamodel.base_models import DocumentStream, InputFormat
        from docling.datamodel.pipeline_options import AcceleratorDevice, AcceleratorOptions, PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as exc:
        raise ResearchError(PARSER_RUNTIME_MISSING, "Docling runtime is not installed") from exc
    try:
        pipeline_options = PdfPipelineOptions(
            artifacts_path=str(artifacts_path),
            enable_remote_services=False,
            allow_external_plugins=False,
            do_ocr=False,
            do_table_structure=True,
            generate_page_images=False,
            generate_picture_images=False,
            do_code_enrichment=False,
            do_formula_enrichment=False,
            do_picture_classification=False,
            do_picture_description=False,
            do_chart_extraction=False,
            document_timeout=300,
            accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CPU, num_threads=4),
        )
        converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
        )
        stream = DocumentStream(name=name, stream=BytesIO(pdf_bytes))
        return converter.convert(stream, max_num_pages=PDF_MAX_PAGES, max_file_size=PDF_MAX_BYTES)
    except ResearchError:
        raise
    except TypeError as exc:
        raise ResearchError(PARSER_RUNTIME_INCOMPATIBLE, "pinned Docling API is unavailable") from exc
    except Exception as exc:
        raise ResearchError(PARSER_FAILED, "Docling conversion failed") from exc


def _json_depth(value: Any, limit: int) -> int:
    def walk(node: Any, depth: int) -> int:
        if depth > limit:
            raise ResearchError(PARSER_OUTPUT_INVALID, "document JSON exceeds depth 64")
        if type(node) is dict:
            deepest = depth
            for item in node.values():
                deepest = max(deepest, walk(item, depth + 1))
            return deepest
        if type(node) is list:
            deepest = depth
            for item in node:
                deepest = max(deepest, walk(item, depth + 1))
            return deepest
        return depth

    return walk(value, 1)


def _write_failure(session: RetainedResearchSession, run_id: str, payload: dict[str, Any]) -> None:
    target = session.path("failed-runs", f"{run_id}.json")
    require_family_slot(session, "failed-runs", target)
    data = jcs_bytes(payload) + b"\n"
    try:
        stage_research(session, ("failed-runs", f"{run_id}.json"), data)
    except (StagingError, ResearchError):
        return


def _complete_run(run_dir: Path) -> bool:
    return all((run_dir / name).is_file() and not (run_dir / name).is_symlink() for name in RUN_NAMES)


def export_run(
    session: RetainedResearchSession,
    *,
    intake_path: Path,
    profile_path: Path,
    artifacts_path: Path,
    run_id: object,
    converter: Converter | None = None,
) -> dict[str, Any]:
    try:
        run = validate_batch_id(run_id)
    except StagingError as exc:
        raise ResearchError(PARSER_RUN_CONFLICT, "run-id is not a legal id", dict(exc.details)) from exc
    intake_session, intake, _raw = load_intake(intake_path)
    if intake_session != session.session_id:
        raise ResearchError(PARSER_SOURCE_UNBOUND, "intake does not belong to this session")
    profile_session = session_from_research_path(profile_path, kind_dir="profile")
    if profile_session != session.session_id:
        raise ResearchError(PARSER_PROFILE_INVALID, "profile does not belong to this session")
    profile, _profile_raw = load_profile(profile_path)
    parser = profile["data"]["parser"]
    pdf_sha = str(intake["data"]["pdf_sha256"])
    blob = session.checkout / ".work" / "blobs" / pdf_sha
    try:
        pdf = read_regular_file(
            blob,
            missing_code=PARSER_SOURCE_UNBOUND,
            unsafe_code=PARSER_SOURCE_UNBOUND,
            changed_code=SOURCE_CHANGED,
            max_bytes=PDF_MAX_BYTES,
            limit_code=PARSER_SOURCE_UNBOUND,
        )
    except SecureIOError as exc:
        raise ResearchError(PARSER_SOURCE_UNBOUND, "intake blob is missing", dict(exc.details)) from exc
    if sha256_bytes(pdf) != pdf_sha:
        raise ResearchError(PARSER_SOURCE_UNBOUND, "intake blob digest differs")
    config_bytes = jcs_bytes(profile["data"]["parser_config"]) + b"\n"
    manifest_bytes = jcs_bytes(profile["data"]["model_manifest"]) + b"\n"
    if sha256_bytes(config_bytes) != parser["config_sha256"] or sha256_bytes(manifest_bytes) != parser["model_manifest_sha256"]:
        raise ResearchError(PARSER_PROFILE_INVALID, "profile config/manifest bytes differ")
    run_dir = session.path("runs", run)
    if run_dir.exists():
        if _complete_run(run_dir):
            return _reuse_run(session, run, intake, profile, pdf, config_bytes, manifest_bytes)
        raise ResearchError(PARSER_RUN_INCOMPLETE, "incomplete run-id cannot be overwritten")
    require_family_slot(session, "runs", run_dir)
    installed_versions()
    started = _utc_now()
    producer = converter if converter is not None else _TEST_CONVERTER
    sock, connect, dns, env = _patch_offline()
    try:
        if producer is None:
            result = _real_convert(
                pdf_bytes=pdf,
                name=f"{pdf_sha}.pdf",
                artifacts_path=artifacts_path,
                options=profile["data"]["parser_config"]["options"],
            )
        else:
            result = producer(pdf_bytes=pdf, name=f"{pdf_sha}.pdf", artifacts_path=artifacts_path)
        if not _status_success(result):
            raise ResearchError(PARSER_FAILED, "Docling conversion did not report SUCCESS")
        document_obj = getattr(result, "document", None)
        exporter = getattr(document_obj, "export_to_dict", None)
        if not callable(exporter):
            raise ResearchError(PARSER_OUTPUT_INVALID, "conversion result has no document export")
        exported = exporter()
        if type(exported) is not dict:
            raise ResearchError(PARSER_OUTPUT_INVALID, "document export must be an object")
        _json_depth(exported, DOCUMENT_JSON_MAX_DEPTH)
        if not _has_nonempty_text(exported):
            raise ResearchError(PARSER_NO_TEXT, "conversion produced no nonempty text")
        pages = exported.get("pages")
        if type(pages) is dict:
            for key, page in pages.items():
                if type(page) is dict and type(page.get("page_no")) is int:
                    if page["page_no"] < 1 or page["page_no"] > int(intake["data"]["page_count"]):
                        raise ResearchError(PARSER_PARTIAL_RESULT, "page provenance exceeds the PDF")
        try:
            document_bytes = dump_float_json(exported)
        except ValueError as exc:
            raise ResearchError(PARSER_OUTPUT_INVALID, "document JSON contains non-finite numbers") from exc
        if len(document_bytes) > DOCUMENT_JSON_MAX_BYTES:
            raise ResearchError(PARSER_OUTPUT_INVALID, "document JSON exceeds 64 MiB")
        parse_float_json(document_bytes, invalid_code=PARSER_OUTPUT_INVALID)
    except BaseException as exc:
        ended = _utc_now()
        code = getattr(exc, "code", PARSER_FAILED) if isinstance(exc, ResearchError) else PARSER_FAILED
        _write_failure(
            session,
            run,
            {
                "code": str(code),
                "message": str(getattr(exc, "message", exc)),
                "started_at": started,
                "ended_at": ended,
                "intake": exact_ref(intake),
                "profile": exact_ref(profile),
                "run_id": run,
            },
        )
        raise
    finally:
        _restore_offline(sock, connect, dns, env)
    ended = _utc_now()
    fingerprint = pipeline_fingerprint(parser)
    run_manifest = {
        "schema": "video-paper-wiki.run-manifest.v1",
        "run_id": run,
        "tool_versions": {
            "vpwiki": VPWIKI_VERSION,
            "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "docling": DOCLING_VERSION,
            "docling_core": DOCLING_CORE_VERSION,
        },
        "input_hashes": {
            "source_sha256": pdf_sha,
            "parser_config_sha256": parser["config_sha256"],
            "model_manifest_sha256": parser["model_manifest_sha256"],
        },
        "output_hashes": {"document_json_sha256": sha256_bytes(document_bytes)},
        "started_at": started,
        "ended_at": ended,
        "error_code": None,
        "pipeline_fingerprint": fingerprint,
    }
    try:
        validate_document(run_manifest, expected_schema="video-paper-wiki.run-manifest.v1")
    except ContractError as exc:
        raise ResearchError(PARSER_OUTPUT_INVALID, str(exc.message), dict(exc.details)) from exc
    run_bytes = jcs_bytes(run_manifest) + b"\n"
    session.verify()
    doc_s = stage_research(session, ("runs", run, "document.json"), document_bytes)
    cfg_s = stage_research(session, ("runs", run, "parser-config.json"), config_bytes)
    man_s = stage_research(session, ("runs", run, "model-manifest.json"), manifest_bytes)
    run_s = stage_research(session, ("runs", run, "run.json"), run_bytes)
    return _result_payload(
        session,
        run,
        intake,
        profile,
        fingerprint,
        document_bytes,
        config_bytes,
        manifest_bytes,
        run_bytes,
        already=all(item.already_staged for item in (doc_s, cfg_s, man_s, run_s)),
    )


def _reuse_run(
    session: RetainedResearchSession,
    run: str,
    intake: dict[str, Any],
    profile: dict[str, Any],
    pdf: bytes,
    config_bytes: bytes,
    manifest_bytes: bytes,
) -> dict[str, Any]:
    run_dir = session.path("runs", run)
    document_bytes = read_regular_file(
        run_dir / "document.json",
        missing_code=PARSER_RUN_INCOMPLETE,
        unsafe_code=PARSER_RUN_INCOMPLETE,
        max_bytes=DOCUMENT_JSON_MAX_BYTES,
        limit_code=PARSER_OUTPUT_INVALID,
    )
    existing_config = (run_dir / "parser-config.json").read_bytes()
    existing_manifest = (run_dir / "model-manifest.json").read_bytes()
    run_bytes = (run_dir / "run.json").read_bytes()
    if existing_config != config_bytes or existing_manifest != manifest_bytes:
        raise ResearchError(PARSER_RUN_CONFLICT, "run-id is bound to a different profile")
    run_doc = parse_float_json(run_bytes, invalid_code=PARSER_OUTPUT_INVALID)
    validate_document(run_doc, expected_schema="video-paper-wiki.run-manifest.v1")
    pdf_sha = str(intake["data"]["pdf_sha256"])
    if run_doc["input_hashes"].get("source_sha256") != pdf_sha or sha256_bytes(pdf) != pdf_sha:
        raise ResearchError(PARSER_RUN_CONFLICT, "run-id is bound to a different source")
    if run_doc["output_hashes"].get("document_json_sha256") != sha256_bytes(document_bytes):
        raise ResearchError(PARSER_RUN_CONFLICT, "stored document hash differs")
    fingerprint = pipeline_fingerprint(profile["data"]["parser"])
    if run_doc.get("pipeline_fingerprint") != fingerprint:
        raise ResearchError(PARSER_RUN_CONFLICT, "stored fingerprint differs")
    return _result_payload(
        session, run, intake, profile, fingerprint, document_bytes, config_bytes, manifest_bytes, run_bytes, already=True
    )


def _result_payload(
    session: RetainedResearchSession,
    run: str,
    intake: dict[str, Any],
    profile: dict[str, Any],
    fingerprint: str,
    document_bytes: bytes,
    config_bytes: bytes,
    manifest_bytes: bytes,
    run_bytes: bytes,
    *,
    already: bool,
) -> dict[str, Any]:
    paths = {
        "document_json": session.posix("runs", run, "document.json"),
        "parser_config": session.posix("runs", run, "parser-config.json"),
        "model_manifest": session.posix("runs", run, "model-manifest.json"),
        "run_manifest": session.posix("runs", run, "run.json"),
    }
    hashes = {
        "document_json": sha256_bytes(document_bytes),
        "parser_config": sha256_bytes(config_bytes),
        "model_manifest": sha256_bytes(manifest_bytes),
        "run_manifest": sha256_bytes(run_bytes),
    }
    return {
        "run_id": run,
        "paths": paths,
        "hashes": hashes,
        "pipeline_fingerprint": fingerprint,
        "intake": exact_ref(intake),
        "profile": exact_ref(profile),
        "state": "staged_extraction",
        "capture_authorized": False,
        "receipt_backed": False,
        "published": False,
        "next_action": "source_analysis",
        "already_staged": already,
    }
