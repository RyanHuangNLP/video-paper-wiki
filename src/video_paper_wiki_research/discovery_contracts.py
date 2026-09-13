"""Closed, content-addressed discovery documents and offline resource validation."""
from __future__ import annotations

import copy
import hashlib
import ipaddress
import re
import unicodedata
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from importlib import resources
from urllib.parse import urlsplit, urlunsplit

from referencing import Registry, Resource

from video_paper_wiki.identity import normalize_doi, normalize_openalex_id
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.secure_io import SecureIOError, parse_strict_json
from video_paper_wiki_research.arxiv_preview import normalize_arxiv
from video_paper_wiki_research.contracts import ResearchError, _Validator, _json_depth

PREFIX = "video-paper-wiki-research."
PROFILE_SHA = "b814cb259070db2b832004acca8a3daf9b97cfde757c055e7c68e80bd285e599"
KINDS = {
    "research-config": "metadata", "research-session": "metadata",
    "research-round-plan": "metadata", "discovery-request": "requests",
    "discovery-observation": "observations", "research-assessment": "decisions",
    "paper-candidate-set": "proposals", "paper-rank": "proposals",
    "research-stop-decision": "proposals", "research-round-event": "metadata",
    "candidate-decision": "decisions", "research-control-event": "decisions",
}
CAPS = {kind: 65536 for kind in KINDS}
CAPS.update({"discovery-observation": 1114112, "research-assessment": 262144,
             "paper-candidate-set": 2097152, "paper-rank": 1048576,
             "research-stop-decision": 262144})
LENSES = ("method", "benchmark", "implementation", "counterevidence", "reproduction")
OPERATIONS = ("lookup", "references", "citations", "related", "topic", "project")
PROVIDERS = ("openalex-rest-normalized-v1", "platform-web-search-normalized-v1")
HARD_LIMITS = {"rounds": 8, "requests": 32, "observations": 32, "per_round_requests": 8,
               "per_page": 20, "results_per_observation": 100, "total_results": 2048,
               "unique_candidates": 256, "payload_bytes": 1048576,
               "total_payload_bytes": 16777216}
REASONS = ("budget_exhausted", "paths_covered", "duplicate_ratio", "yield_below_threshold")
SCHEMA_FILES = ("discovery-common.v1.schema.json",) + tuple(k + ".v1.schema.json" for k in KINDS)
RESOURCE_PATHS = tuple("schemas/" + name for name in SCHEMA_FILES) + (
    "profiles/discovery-v1.json", "prompts/discovery-assessment-v1.md")
_BOUND = ContextVar("discovery_retained_resources", default=None)


def fail(code, message, **details):
    raise ResearchError(code, message, details, exit_code=75 if code == "DISCOVERY_BUSY" else 2)


def invalid(message, **details):
    fail("DISCOVERY_INPUT_INVALID", message, **details)


def graph_invalid(message, **details):
    fail("DISCOVERY_GRAPH_INVALID", message, **details)


def limit(message, **details):
    fail("DISCOVERY_LIMIT_EXCEEDED", message, **details)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def ordered(values):
    return sorted(values, key=canonicalize)


def unique(values):
    return [v for _, v in sorted({canonicalize(v): v for v in values}.items())]


def require_set(values, label):
    if values != unique(values):
        invalid("set array must be canonical and duplicate-free", field=label)


def preflight(value):
    stack, count = [(value, 0, "")], 0
    text_fields = {"text", "summary", "statement", "reason", "message"}
    while stack:
        item, depth, key = stack.pop()
        count += 1
        if depth > 32 or count > 500000:
            limit("discovery JSON structural bound exceeded")
        if type(item) is dict:
            for name, child in item.items():
                if type(name) is not str:
                    invalid("JSON keys must be strings")
                stack.append((name, depth + 1, ""))
                stack.append((child, depth + 1, name))
        elif type(item) is list:
            stack.extend((child, depth + 1, key) for child in item)
        elif type(item) is str:
            try:
                raw = item.encode("utf-8")
            except UnicodeError:
                invalid("JSON contains invalid Unicode")
            if len(raw) > 65536 or unicodedata.normalize("NFC", item) != item:
                invalid("strings must be bounded NFC text")
            for char in item:
                code = ord(char)
                if (code < 32 or 127 <= code <= 159) and not (key in text_fields and char in "\t\n"):
                    invalid("control character outside declared evidence text", field=key)
        elif type(item) is int:
            if abs(item) > 9007199254740991:
                invalid("integer exceeds exact JCS range")
        elif item is not None and type(item) is not bool:
            invalid("discovery JSON allows integer numbers only")


def parse_json(raw, *, maximum=2097152):
    if type(raw) is not bytes or len(raw) > maximum:
        limit("JSON input exceeds its byte bound", maximum=maximum)
    try:
        _json_depth(raw.decode("utf-8"), limit=32, code="DISCOVERY_INPUT_INVALID")
        result = parse_strict_json(raw, invalid_code="DISCOVERY_INPUT_INVALID")
        preflight(result)
        return result
    except (ValueError, UnicodeError, RecursionError, SecureIOError) as exc:
        if isinstance(exc, ResearchError):
            raise
        invalid("input must be bounded strict UTF-8 JSON")


def timestamp(value):
    try:
        if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value) is None:
            raise ValueError
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        invalid("timestamp must be a calendar-valid whole-second UTC time")


def source_url(value, *, grouping=False):
    try:
        if type(value) is not str or len(value.encode("utf-8")) > 4094 or "\\" in value or any(ord(c) < 33 or 127 <= ord(c) <= 159 for c in value):
            raise ValueError
        parts = urlsplit(value)
        host = parts.hostname
        if (parts.scheme.lower() != "https" or not host or parts.username is not None
                or parts.password is not None or "%" in host or host.endswith(".")
                or host.lower() == "localhost" or host.lower().endswith((".localhost", ".local"))):
            raise ValueError
        port = parts.port
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if "." not in host or not host.isascii():
                raise ValueError
        else:
            if not address.is_global:
                raise ValueError
        if port not in (None, 443):
            raise ValueError
        if grouping:
            return urlunsplit(("https", host.lower(), parts.path, parts.query, ""))
        return value
    except (ValueError, UnicodeError):
        invalid("source locator must be a bounded public HTTPS URL without credentials")


def identifier(value, *, normalize=False):
    if type(value) is not dict or set(value) != {"namespace", "value", "version"}:
        invalid("identifier must contain namespace, value and version")
    namespace, body, version = value["namespace"], value["value"], value["version"]
    if type(body) is not str or len(body) > 4094 or namespace not in {"doi", "arxiv", "openalex"}:
        invalid("identifier namespace or value is invalid")
    try:
        if namespace == "arxiv":
            canonical, parsed_version = normalize_arxiv(body)
            if version is not None and (type(version) is not int or not 1 <= version <= 9999):
                invalid("arXiv version is outside 1..9999")
            if parsed_version is not None and version not in (None, parsed_version):
                invalid("arXiv version declarations conflict")
            version = parsed_version if parsed_version is not None else version
        elif namespace == "doi":
            canonical = normalize_doi(body).removeprefix("doi:")
            if version is not None:
                invalid("DOI versions must be null")
        else:
            canonical = normalize_openalex_id(body).removeprefix("openalex:")
            if re.fullmatch(r"W[1-9][0-9]*", canonical) is None or version is not None:
                invalid("OpenAlex identifier or version is invalid")
        result = {"namespace": namespace, "value": canonical, "version": version}
        if len(canonical) > 256 or not normalize and result != value:
            invalid("sealed identifier is not canonical")
        return result
    except ValueError as exc:
        if isinstance(exc, ResearchError) and exc.code.startswith("DISCOVERY_"):
            raise
        invalid("identifier is not supported or canonical")


def unversioned(value):
    return {"namespace": value["namespace"], "value": value["value"]}


def canonical_ids(values):
    return unique([identifier(v, normalize=True) for v in values])


def spec_key(spec):
    return sha(b"rw3/request-spec-v1\0" + canonicalize({k: v for k, v in spec.items() if k != "request_key"}))


def _build_registry(raws):
    schemas, entries = {}, []
    for name in SCHEMA_FILES:
        schema = parse_json(raws["schemas/" + name])
        _Validator.check_schema(schema)
        schemas[name] = schema
        entries.append((schema["$id"], Resource.from_contents(schema)))
    profile_raw = raws["profiles/discovery-v1.json"]
    if sha(profile_raw) != PROFILE_SHA:
        invalid("discovery profile differs from the frozen provider/resource contract")
    profile = parse_json(profile_raw)
    if profile["kind_families"] != KINDS or profile["saved_byte_caps"] != CAPS or profile["hard_limits"] != HARD_LIMITS:
        invalid("discovery code and profile constants differ")
    if not raws["prompts/discovery-assessment-v1.md"]:
        invalid("discovery assessment prompt is empty")
    return Registry().with_resources(entries), schemas, profile, raws


@contextmanager
def bound_resources(raws):
    token = _BOUND.set(_build_registry(raws))
    try:
        yield
    finally:
        _BOUND.reset(token)


def resource_state():
    state = _BOUND.get()
    if state is not None:
        return state
    root = resources.files("video_paper_wiki_research")
    try:
        return _build_registry({name: root.joinpath(name).read_bytes() for name in RESOURCE_PATHS})
    except OSError:
        invalid("discovery package resource is missing")


def validate_shape(value, name, *, definition=False):
    preflight(value)
    registry, schemas, _, _ = resource_state()
    if definition:
        common = schemas["discovery-common.v1.schema.json"]
        schema = {"$ref": common["$id"] + "#/$defs/" + name}
    else:
        if name not in KINDS:
            invalid("unknown discovery artifact kind")
        schema = schemas[name + ".v1.schema.json"]
    error = next(_Validator(schema, registry=registry).iter_errors(value), None)
    if error is not None:
        invalid("discovery object does not match its closed schema", pointer="/" + "/".join(str(p) for p in error.absolute_path), keyword=error.validator)


def _semantic_walk(value, key=""):
    if type(value) is dict:
        if set(value) == {"namespace", "value", "version"}:
            identifier(value)
        if set(value) == {"namespace", "value"}:
            identifier({**value, "version": None})
        if "identity_source" in value:
            name = "tool_name" if "tool_name" in value else "value"
            if not value[name].strip() or value["identity_source"] != "unknown" and value[name] == "unknown":
                invalid("reported identity must be nonempty and consistent")
        for name, child in value.items():
            _semantic_walk(child, name)
    elif type(value) is list:
        for child in value:
            _semantic_walk(child, key)
    elif type(value) is str:
        if key in {"observed_at", "recorded_at"}:
            timestamp(value)
        elif key in {"published_at", "latest_published_at"}:
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except ValueError:
                invalid("publication date is not calendar-valid")
        elif key in {"locator", "url"}:
            source_url(value)
        elif key == "provider_score" and value in {"-0"}:
            invalid("provider decimal is not canonical")
        elif not value.strip():
            invalid("declared strings must contain non-whitespace text", field=key)


def config_input(value):
    if type(value) is not dict:
        invalid("configuration input must be an object")
    result = copy.deepcopy(value)
    try:
        for seed in result["seeds"]:
            seed["ids"] = canonical_ids(seed["ids"])
    except (KeyError, TypeError):
        invalid("configuration seed input is malformed")
    validate_shape(result, "config", definition=True)
    _semantic_walk(result)
    if [v["lens"] for v in result["lenses"]] != list(LENSES):
        invalid("all five lenses must appear in fixed profile order")
    keys = [s["key"] for s in result["seeds"]]
    if len(keys) != len(set(keys)):
        invalid("seed keys must be distinct")
    for seed in result["seeds"]:
        if len({i["namespace"] for i in seed["ids"]}) != len(seed["ids"]):
            invalid("seed has more than one identifier in a namespace")
    return result


def semantics(kind, data):
    _semantic_walk(data)
    if kind == "research-config":
        if config_input(data) != data:
            invalid("sealed config is not canonical")
    elif kind == "research-round-plan":
        specs = data["request_specs"]
        keys = [s["request_key"] for s in specs]
        if keys != sorted(set(keys)):
            invalid("plan specifications must be sorted by unique request key")
        for spec in specs:
            validate_spec(spec)
    elif kind == "discovery-request":
        validate_spec(data["spec"])
        if data["request_key"] != data["spec"]["request_key"]:
            invalid("request key and repeated specification disagree")
    elif kind == "discovery-observation":
        outcome, payload, failure = data["outcome"], data["payload"], data["failure"]
        if ((outcome == "success" and (payload is None or failure is not None))
                or (outcome == "partial" and (payload is None or failure is None))
                or (outcome not in {"success", "partial"} and (payload is not None or failure is None))):
            invalid("outcome payload and failure branches disagree")
        if payload is not None:
            if len(canonicalize(payload)) > HARD_LIMITS["payload_bytes"]:
                limit("normalized observation payload exceeds one MiB")
            for ordinal, result in enumerate(payload["results"], 1):
                if result["ordinal"] != ordinal:
                    invalid("result ordinals must be the exact provider order 1..N")
                require_set(result["ids"], "ids")
                require_set(result["identity_links"], "identity_links")
                for link in result["identity_links"]:
                    if link["left"] not in result["ids"] or link["right"] not in result["ids"]:
                        invalid("identity-link endpoints must occur in that result")
                for field in ("referenced_ids", "related_ids"):
                    if result[field] is not None:
                        require_set(result[field], field)
    elif kind == "research-assessment":
        if [v["lens"] for v in data["lenses"]] != list(LENSES):
            invalid("assessment must contain all five lenses in order")
        require_set(data["observations"], "observations")
        for lens in data["lenses"]:
            require_set(lens["evidence"], "evidence")
            if (lens["state"] == "covered" and (not lens["evidence"] or lens["reason"] is not None)
                    or lens["state"] == "not_applicable" and (lens["evidence"] or lens["reason"] is None)
                    or lens["state"] == "gap" and lens["reason"] is None):
                invalid("assessment state requires consistent evidence and rationale")
    elif kind == "candidate-decision":
        selected = data["selected_arxiv"]
        if (data["action"] == "preview" and (selected is None or selected["namespace"] != "arxiv")
                or data["action"] != "preview" and selected is not None):
            invalid("only preview decisions select an observed arXiv identity")


def validate_spec(spec):
    validate_shape(spec, "spec", definition=True)
    _semantic_walk(spec)
    require_set(spec["subject_ids"], "subject_ids")
    if spec["neighbor_ids"] is not None:
        require_set(spec["neighbor_ids"], "neighbor_ids")
    if spec_key(spec) != spec["request_key"]:
        invalid("specification key does not hash its complete fields")


def saved_bytes(document):
    preflight(document)
    kind = document.get("kind") if type(document) is dict else None
    if kind not in KINDS:
        invalid("unknown discovery artifact kind")
    raw = canonicalize(document) + b"\n"
    if len(raw) > CAPS[kind]:
        limit("serialized discovery artifact exceeds its saved-byte bound", kind=kind, maximum=CAPS[kind])
    return raw


def reference(document):
    return {"id": document["id"], "sha256": sha(saved_bytes(document))}


def seal(kind, data):
    if kind not in KINDS:
        invalid("unknown discovery artifact kind")
    core = {"schema_version": PREFIX + kind + ".v1", "kind": kind, "data": copy.deepcopy(data)}
    preflight(core)
    digest = sha(canonicalize(core))
    document = {**core, "id": "rw3:" + kind + ":" + digest, "content_sha256": digest}
    return validate(document, kind)


def validate(document, kind=None):
    if type(document) is not dict:
        invalid("discovery artifact must be an object")
    actual = document.get("kind")
    if kind is not None and kind != actual:
        invalid("artifact has the wrong kind")
    validate_shape(document, actual)
    semantics(actual, document["data"])
    core = {k: document[k] for k in ("schema_version", "kind", "data")}
    digest = sha(canonicalize(core))
    if document["content_sha256"] != digest or document["id"] != "rw3:" + actual + ":" + digest:
        invalid("artifact content identity is not byte-exact")
    saved_bytes(document)
    return document
