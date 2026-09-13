"""Research envelope, schema, and error codes for manual-pdf-extraction-v1.

Internal helpers reused from the same-repository engine, without changing
their semantics: integer JCS, identity, strict JSON, envelope, schema
validation of the legacy paper-analysis draft, and the Docling artifact
package function.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from importlib import resources
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from jsonschema.exceptions import best_match
from jsonschema.validators import extend
from referencing import Registry, Resource

from video_paper_wiki.envelope import EXIT_REFUSAL, EXIT_SUCCESS, EXIT_TEMPORARY_FAILURE
from video_paper_wiki.jcs import CanonicalJsonError, canonicalize
from video_paper_wiki.secure_io import SecureIOError, parse_strict_json

SCHEMA_PREFIX = "video-paper-wiki-research."
KIND_TO_STEM = {
    "intake": "manual-pdf-intake.v1",
    "profile": "parser-profile.v1",
    "context": "source-analysis-context.v1",
    "proposal": "source-analysis-proposal.v1",
}
STEM_TO_KIND = {value: key for key, value in KIND_TO_STEM.items()}
SCHEMA_FILES = (
    "common.v1.schema.json",
    "manual-pdf-intake.v1.schema.json",
    "parser-profile.v1.schema.json",
    "source-analysis-context.v1.schema.json",
    "source-analysis-proposal.v1.schema.json",
)
JSON_MAX_BYTES = 8 * 1024 * 1024
JSON_MAX_DEPTH = 32
MAX_STRING_BYTES = 262144
DOCUMENT_JSON_MAX_BYTES = 64 * 1024 * 1024
DOCUMENT_JSON_MAX_DEPTH = 64
PDF_MAX_BYTES = 64 * 1024 * 1024
PDF_MAX_PAGES = 300
PDF_MAGIC = b"%PDF-"
FAMILY_LIMIT = 256
INVENTORY_LIMIT = 20000
BLOCK_LIMIT = 128
TEXT_BUDGET = 262144
MODEL_MAX_FILES = 4096
MODEL_MAX_DEPTH = 16
MODEL_FILE_MAX = 4 * 1024 * 1024 * 1024
MODEL_TOTAL_MAX = 32 * 1024 * 1024 * 1024
DOCLING_VERSION = "2.117.0"
DOCLING_CORE_VERSION = "2.92.0"
PARSER_CONFIG_SCHEMA = "manual-pdf-parser-config.v1"
MODEL_MANIFEST_SCHEMA = "manual-pdf-model-manifest.v1"
TRANSPORT_SCHEMA = "video-paper-wiki-research.paper-analysis-transport.v1"
LEGACY_DRAFT_SCHEMA = "video-paper-wiki.paper-analysis-draft.v1"
PROMPT_RESOURCE = "paper-analysis-v1.md"

MANUAL_PDF_INVALID = "MANUAL_PDF_INVALID"
MANUAL_PDF_CHANGED = "MANUAL_PDF_CHANGED"
INTAKE_INVALID = "INTAKE_INVALID"
INTAKE_BINDING_MISMATCH = "INTAKE_BINDING_MISMATCH"
PARSER_PROFILE_INVALID = "PARSER_PROFILE_INVALID"
PARSER_MODELS_MISSING = "PARSER_MODELS_MISSING"
PARSER_PROFILE_CHANGED = "PARSER_PROFILE_CHANGED"
PARSER_RUNTIME_MISSING = "PARSER_RUNTIME_MISSING"
PARSER_RUNTIME_INCOMPATIBLE = "PARSER_RUNTIME_INCOMPATIBLE"
PARSER_NETWORK_REFUSED = "PARSER_NETWORK_REFUSED"
PARSER_SOURCE_UNBOUND = "PARSER_SOURCE_UNBOUND"
PARSER_FAILED = "PARSER_FAILED"
PARSER_PARTIAL_RESULT = "PARSER_PARTIAL_RESULT"
PARSER_NO_TEXT = "PARSER_NO_TEXT"
PARSER_OUTPUT_INVALID = "PARSER_OUTPUT_INVALID"
PARSER_RUN_CONFLICT = "PARSER_RUN_CONFLICT"
PARSER_RUN_INCOMPLETE = "PARSER_RUN_INCOMPLETE"
SOURCE_CONTEXT_INVALID = "SOURCE_CONTEXT_INVALID"
SOURCE_CONTEXT_LIMIT = "SOURCE_CONTEXT_LIMIT"
SOURCE_ANALYSIS_INVALID = "SOURCE_ANALYSIS_INVALID"
SOURCE_ANALYSIS_EMPTY = "SOURCE_ANALYSIS_EMPTY"
SOURCE_ANALYSIS_BINDING_MISMATCH = "SOURCE_ANALYSIS_BINDING_MISMATCH"

PARSER_CONFIG = {
    "schema": PARSER_CONFIG_SCHEMA,
    "engine": "docling",
    "engine_version": DOCLING_VERSION,
    "core_version": DOCLING_CORE_VERSION,
    "options": {
        "enable_remote_services": False,
        "allow_external_plugins": False,
        "do_ocr": False,
        "do_table_structure": True,
        "generate_page_images": False,
        "generate_picture_images": False,
        "do_code_enrichment": False,
        "do_formula_enrichment": False,
        "do_picture_classification": False,
        "do_picture_description": False,
        "do_chart_extraction": False,
        "document_timeout": 300,
        "accelerator_device": "cpu",
        "num_threads": 4,
    },
}

SECTION_SPECS: tuple[tuple[str, str], ...] = (
    ("one_sentence_conclusion", "一句话结论"),
    ("research_question", "研究问题"),
    ("method", "方法"),
    ("representation_architecture", "表示与架构"),
    ("training_data", "训练与数据"),
    ("experiments_results", "实验与结果"),
    ("limitations", "局限"),
    ("code_resources", "代码与资源"),
    ("evidence_status", "证据状态"),
    ("related", "关联"),
)

_TYPES = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
).redefine(
    "number",
    lambda _checker, value: type(value) in (int, float) and type(value) is not bool,
)
_Validator = extend(Draft202012Validator, type_checker=_TYPES)


class ResearchError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        *,
        exit_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = {} if details is None else dict(details)
        if exit_code is None:
            self.exit_code = EXIT_TEMPORARY_FAILURE if code in {
                MANUAL_PDF_CHANGED,
                PARSER_PROFILE_CHANGED,
                "SOURCE_CHANGED",
                "STAGING_CONFLICT",
            } else EXIT_REFUSAL
        else:
            self.exit_code = exit_code


def _pointer(path: list[Any]) -> str:
    if not path:
        return ""
    return "/" + "/".join(str(item).replace("~", "~0").replace("/", "~1") for item in path)


def _schema_text(filename: str) -> str:
    try:
        traversable = resources.files("video_paper_wiki_research").joinpath("schemas", filename)
        return traversable.read_text(encoding="utf-8")
    except (OSError, FileNotFoundError, UnicodeError) as exc:
        raise ResearchError(INTAKE_INVALID, f"schema resource is missing: {filename}") from exc


@lru_cache(maxsize=1)
def _registry() -> tuple[Registry, dict[str, dict[str, Any]]]:
    entries: list[tuple[str, Resource]] = []
    by_title: dict[str, dict[str, Any]] = {}
    for filename in SCHEMA_FILES:
        schema = json.loads(_schema_text(filename))
        if type(schema) is not dict:
            raise ResearchError(INTAKE_INVALID, f"schema is not an object: {filename}")
        schema_id = str(schema.get("$id", ""))
        title = str(schema.get("title", ""))
        if not schema_id or not title:
            raise ResearchError(INTAKE_INVALID, f"schema is missing $id or title: {filename}")
        entries.append((schema_id, Resource.from_contents(schema)))
        by_title[title] = schema
    return Registry().with_resources(entries), by_title


def schema_by_title(title: str) -> dict[str, Any]:
    _reg, by_title = _registry()
    schema = by_title.get(title)
    if schema is None:
        raise ResearchError(INTAKE_INVALID, f"unknown schema: {title}", {"schema": title})
    return schema


def _raise_schema(error: ValidationError, schema_name: str) -> None:
    match = best_match([error]) if error else error
    target = match if match is not None else error
    raise ResearchError(
        INTAKE_INVALID if "intake" in schema_name else (
            PARSER_PROFILE_INVALID if "parser-profile" in schema_name else (
                SOURCE_CONTEXT_INVALID if "context" in schema_name else SOURCE_ANALYSIS_INVALID
            )
        ),
        str(target.message),
        {
            "schema": schema_name,
            "instance_pointer": _pointer(list(target.absolute_path)),
            "keyword": str(target.validator or "unknown"),
        },
    )


def _validate_shape(document: Mapping[str, Any], schema_name: str) -> None:
    schema = schema_by_title(schema_name)
    registry, _by_title = _registry()
    validator = _Validator(schema, registry=registry, format_checker=FormatChecker())
    error = next(validator.iter_errors(document), None)
    if error is not None:
        _raise_schema(error, schema_name)


def _walk_strings(value: Any, *, limit: int = MAX_STRING_BYTES) -> None:
    pending: list[Any] = [value]
    while pending:
        current = pending.pop()
        if type(current) is dict:
            pending.extend(current.keys())
            pending.extend(current.values())
        elif type(current) is list:
            pending.extend(current)
        elif type(current) is str:
            if len(current.encode("utf-8")) > limit:
                raise ResearchError(INTAKE_INVALID, "string exceeds the UTF-8 byte limit")


def _json_depth(text: str, *, limit: int, code: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > limit:
                raise ResearchError(code, "JSON nesting exceeds the supported limit")
        elif char in "]}":
            depth -= 1


def parse_envelope_json(data: bytes, *, invalid_code: str) -> Any:
    if len(data) > JSON_MAX_BYTES:
        raise ResearchError(invalid_code, "JSON exceeds the 8 MiB limit")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ResearchError(invalid_code, "JSON is not valid UTF-8") from exc
    _json_depth(text, limit=JSON_MAX_DEPTH, code=invalid_code)
    try:
        value = parse_strict_json(data, invalid_code=invalid_code)
    except SecureIOError as exc:
        raise ResearchError(invalid_code, str(exc.message), dict(exc.details)) from exc
    _walk_strings(value)
    return value


def parse_float_json(data: bytes, *, invalid_code: str) -> Any:
    if len(data) > DOCUMENT_JSON_MAX_BYTES:
        raise ResearchError(invalid_code, "document JSON exceeds 64 MiB")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ResearchError(invalid_code, "document JSON is not valid UTF-8") from exc
    _json_depth(text, limit=DOCUMENT_JSON_MAX_DEPTH, code=invalid_code)

    def _reject_constant(_value: str) -> Any:
        raise ResearchError(invalid_code, "document JSON must not contain NaN or Infinity")

    def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise ResearchError(invalid_code, "document JSON must not contain duplicate keys")
            out[key] = value
        return out

    decoder = json.JSONDecoder(parse_constant=_reject_constant, object_pairs_hook=_no_duplicate_keys)
    try:
        obj, index = decoder.raw_decode(text.lstrip(" \t\r\n"))
    except ResearchError:
        raise
    except json.JSONDecodeError as exc:
        raise ResearchError(invalid_code, "document JSON is invalid") from exc
    trailing = text[len(text) - len(text.lstrip(" \t\r\n")) + index :]
    if trailing.strip(" \t\r\n"):
        raise ResearchError(invalid_code, "document JSON has trailing data")
    return obj


def dump_float_json(value: Any) -> bytes:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return (text + "\n").encode("utf-8")


def jcs_bytes(value: Any) -> bytes:
    try:
        return canonicalize(value)
    except CanonicalJsonError as exc:
        raise ResearchError(INTAKE_INVALID, str(exc.message), dict(exc.details or {})) from exc


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_sha256(schema: str, data: Mapping[str, Any]) -> str:
    return sha256_bytes(jcs_bytes({"schema": schema, "data": data}))


def envelope_id(kind: str, digest: str) -> str:
    return f"mp1-{kind}-{digest}"


def seal_document(kind: str, data: Mapping[str, Any]) -> dict[str, Any]:
    stem = KIND_TO_STEM[kind]
    schema = SCHEMA_PREFIX + stem
    digest = content_sha256(schema, data)
    document = {
        "schema": schema,
        "id": envelope_id(kind, digest),
        "content_sha256": digest,
        "data": data,
    }
    validate_document(document, expected_kind=kind)
    return document


def saved_bytes(document: Mapping[str, Any]) -> bytes:
    return jcs_bytes(document) + b"\n"


def exact_ref(document: Mapping[str, Any]) -> dict[str, str]:
    return {"id": str(document["id"]), "sha256": sha256_bytes(saved_bytes(document))}


def validate_document(document: object, *, expected_kind: str) -> dict[str, Any]:
    if type(document) is not dict:
        raise ResearchError(INTAKE_INVALID, "document must be an object")
    stem = KIND_TO_STEM[expected_kind]
    schema_name = SCHEMA_PREFIX + stem
    _validate_shape(document, schema_name)
    data = document["data"]
    digest = content_sha256(schema_name, data)
    if document["content_sha256"] != digest:
        raise ResearchError(
            INTAKE_INVALID if expected_kind == "intake" else (
                PARSER_PROFILE_INVALID if expected_kind == "profile" else (
                    SOURCE_CONTEXT_INVALID if expected_kind == "context" else SOURCE_ANALYSIS_INVALID
                )
            ),
            "content_sha256 does not match JCS({schema,data})",
        )
    expected_id = envelope_id(expected_kind, digest)
    if document["id"] != expected_id:
        raise ResearchError(INTAKE_INVALID, "document id does not match content hash")
    return document


def load_prompt_bytes() -> bytes:
    try:
        text = resources.files("video_paper_wiki_research").joinpath("prompts", PROMPT_RESOURCE).read_text(
            encoding="utf-8"
        )
    except (OSError, FileNotFoundError, UnicodeError) as exc:
        raise ResearchError(SOURCE_CONTEXT_INVALID, "task prompt resource is missing") from exc
    return text.encode("utf-8")


def task_prompt_bytes(context_data: Mapping[str, Any]) -> bytes:
    payload = {key: value for key, value in context_data.items() if key != "prompt_sha256"}
    return load_prompt_bytes() + b"\n" + jcs_bytes(payload)


def identity_component_ok(value: object) -> bool:
    if type(value) is not dict or set(value) != {"value", "identity_source", "reason"}:
        return False
    source = value["identity_source"]
    raw = value["value"]
    reason = value["reason"]
    if source not in {"platform_reported", "self_reported", "unknown"}:
        return False
    if type(raw) is not str or not raw:
        return False
    if source == "unknown":
        return raw == "unknown" and type(reason) is str and bool(reason.strip())
    return raw != "unknown" and reason is None
