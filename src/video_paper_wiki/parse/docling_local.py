"""Local-only Docling adapter. Never downloads models or calls remote services."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class ParserUnavailable(RuntimeError):
    """docling extra is missing, or parser models have not been fetched."""


def _env_path(name: str) -> Path | None:
    raw = os.environ.get(name)
    if not raw:
        return None
    return Path(raw)


def _is_usable_artifacts_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    markers = {".safetensors", ".onnx", ".pt", ".pth", ".bin"}
    try:
        entries = list(path.iterdir())
    except OSError:
        return False
    for entry in entries:
        if entry.is_file() and (entry.suffix in markers or entry.name == "config.json"):
            return True
        if entry.is_dir() and (
            (entry / "config.json").is_file()
            or (entry / "model.safetensors").is_file()
            or (entry / "model_artifacts").is_dir()
        ):
            return True
    return False


def resolve_local_artifacts_path() -> Path | None:
    """Return a local artifacts dir only when models already exist. Never fetch."""

    for name in ("DOCLING_ARTIFACTS_PATH", "DOCLING_SERVE_ARTIFACTS_PATH"):
        env_path = _env_path(name)
        if env_path is None:
            continue
        return env_path if _is_usable_artifacts_dir(env_path) else None
    default = Path.home() / ".cache" / "docling" / "models"
    return default if _is_usable_artifacts_dir(default) else None


def _force_offline_env() -> None:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"


def _is_missing_model_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    needles = (
        "offline",
        "huggingface",
        "hf_hub",
        "artifacts",
        "filenotfound",
        "not found",
        "local_files_only",
        "enable_remote",
        "parser model",
        "safetensors",
    )
    return any(needle in text for needle in needles)


def _title_from_result(result: Any) -> str:
    document = getattr(result, "document", result)
    iterate = getattr(document, "iterate_items", None)
    if callable(iterate):
        for item, _level in iterate():
            text = getattr(item, "text", None)
            if not text:
                continue
            label = getattr(item, "label", None)
            label_s = str(label).lower() if label is not None else ""
            if label_s.endswith("title") or label_s == "title":
                return str(text).strip()
    meta = getattr(document, "metadata", None)
    if isinstance(meta, dict):
        title = meta.get("title")
        if title:
            return str(title).strip()
    name = getattr(document, "name", None)
    if name:
        return str(name).strip()
    return ""


def parse_pdf_to_draft_fields(pdf_path: Path) -> dict[str, str]:
    """Parse a local PDF with Docling. Fail closed; never download."""

    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as exc:
        raise ParserUnavailable("docling extra is not installed") from exc

    artifacts = resolve_local_artifacts_path()
    if artifacts is None:
        raise ParserUnavailable("parser models are not fetched")

    _force_offline_env()
    try:
        pipeline_options = PdfPipelineOptions(
            enable_remote_services=False,
            artifacts_path=str(artifacts),
        )
        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )
        result = converter.convert(str(pdf_path))
    except ParserUnavailable:
        raise
    except Exception as exc:
        if _is_missing_model_error(exc):
            raise ParserUnavailable("parser models are not fetched") from exc
        raise

    return {"title": _title_from_result(result), "title_zh": ""}
