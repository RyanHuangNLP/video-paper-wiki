"""Offline registry and exact reference graph for the abstract-only preview flow."""
from __future__ import annotations

import copy
import hashlib
import ipaddress
import json
from datetime import datetime, timezone
from functools import lru_cache
from importlib import resources

from referencing import Registry, Resource

from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.secure_io import parse_strict_json
from video_paper_wiki_research.contracts import ResearchError, _Validator, _json_depth

MAX_BYTES = 1048576
MAX_DEPTH = 32
KINDS = {"request": "connector-request.v1", "observation": "connector-observation.v1",
         "metadata": "arxiv-metadata.v1", "preview": "paper-preview.v1", "decision": "preview-decision.v1"}
SCHEMA_FILES = tuple(stem + ".schema.json" for stem in KINDS.values()) + (
    "preview-common.v1.schema.json", "skill-contract.v1.schema.json")
PREFIX = "video-paper-wiki-research."
BUDGET = {"max_requests": 1, "deadline_seconds": 20, "max_normalized_bytes": MAX_BYTES,
          "max_transport_bytes": MAX_BYTES, "min_interval_seconds": 3, "max_redirects": 2}
SECTIONS = ("one_sentence", "research_question", "method", "contributions_results", "limitations", "relevance")
VERSION_FIELDS = ("entity_id", "requested_version", "resolved_version", "latest_at_observation",
                  "other_versions_exist", "observed_at")


def fail(code: str, message: str, **details) -> None:
    raise ResearchError(code, message, details, exit_code=75 if code in {"DECISION_CONFLICT", "STAGING_CONFLICT"} else 2)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def timestamp(value: object) -> datetime:
    try:
        if type(value) is not str or len(value) != 20:
            raise ValueError
        result = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if result.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
            raise ValueError
        return result
    except ValueError:
        fail("ARTIFACT_INVALID", "timestamp must be a valid canonical UTC time")


def current_time() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def preflight(value: object, *, code: str = "ARTIFACT_INVALID") -> None:
    stack, count = [(value, 0)], 0
    while stack:
        item, depth = stack.pop()
        count += 1
        if depth > MAX_DEPTH or count > 100000:
            fail(code, "JSON structure exceeds preview limits")
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str:
                    fail(code, "JSON keys must be strings")
                stack.extend(((key, depth + 1), (child, depth + 1)))
        elif type(item) is list:
            stack.extend((child, depth + 1) for child in item)
        elif type(item) is str:
            try:
                size = len(item.encode("utf-8"))
            except UnicodeError:
                fail(code, "JSON contains invalid Unicode")
            if size > MAX_BYTES or "\0" in item:
                fail(code, "JSON string is too large or contains NUL")
        elif item is not None and type(item) not in {bool, int}:
            fail(code, "preview JSON permits only integer numbers")
        elif type(item) is int and abs(item) > 9007199254740991:
            fail(code, "JSON integer exceeds exact range")


def parse_json(raw: bytes, *, code: str = "ARTIFACT_INVALID") -> object:
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        fail("RESPONSE_TOO_LARGE", "preview JSON exceeds one MiB")
    try:
        text = raw.decode("utf-8")
        _json_depth(text, limit=MAX_DEPTH, code=code)
        value = parse_strict_json(raw, invalid_code=code)
        preflight(value, code=code)
        return value
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, ResearchError):
            raise
        fail(code, "input must be bounded strict UTF-8 JSON")


def resource_bytes(filename: str) -> bytes:
    if filename not in SCHEMA_FILES and filename != "paper-preview-v1.md":
        fail("ARTIFACT_INVALID", "unknown preview resource")
    family = "prompts" if filename.endswith(".md") else "schemas"
    try:
        return resources.files("video_paper_wiki_research").joinpath(family, filename).read_bytes()
    except (OSError, UnicodeError):
        fail("ARTIFACT_INVALID", "preview package resource is unavailable")


@lru_cache(maxsize=1)
def registry():
    entries, by_title = [], {}
    for filename in SCHEMA_FILES:
        document = json.loads(resource_bytes(filename))
        _Validator.check_schema(document)
        entries.append((document["$id"], Resource.from_contents(document)))
        by_title[document["title"]] = document
    return Registry().with_resources(entries), by_title


def validate_shape(document: object, stem: str, *, code: str = "ARTIFACT_INVALID") -> None:
    preflight(document, code=code)
    reg, schemas = registry()
    schema = schemas.get(PREFIX + stem)
    if schema is None:
        fail(code, "unknown preview schema")
    error = next(_Validator(schema, registry=reg).iter_errors(document), None)
    if error is not None:
        fail(code, "preview object does not match its closed schema",
             pointer="/" + "/".join(str(p) for p in error.absolute_path), keyword=error.validator)


def saved_bytes(document: dict) -> bytes:
    preflight(document)
    raw = canonicalize(document) + b"\n"
    if len(raw) > MAX_BYTES:
        fail("RESPONSE_TOO_LARGE", "serialized preview object exceeds one MiB")
    return raw


def reference(document: dict) -> dict:
    return {"id": document["id"], "sha256": sha(saved_bytes(document))}


def _ref_kind(ref: dict, kind: str) -> None:
    if not ref["id"].startswith("rw1:" + kind + ":"):
        fail("ARTIFACT_BINDING_MISMATCH", "reference points to the wrong artifact kind")


def _identity(value: dict) -> None:
    if not value["value"].strip():
        fail("PREVIEW_PROPOSAL_INVALID", "identity value must contain text")
    if value["identity_source"] == "unknown":
        if value["value"] != "unknown" or not value["reason"] or not value["reason"].strip():
            fail("PREVIEW_PROPOSAL_INVALID", "unknown identity needs a reason and literal unknown value")
    elif value["value"] == "unknown" or value["reason"] is not None:
        fail("PREVIEW_PROPOSAL_INVALID", "known identity and unknown reason disagree")


def _pair(pair: dict) -> None:
    if pair["value"] is None:
        if not pair["unavailable_reason"] or not pair["unavailable_reason"].strip():
            fail("OBSERVATION_PROFILE_INSUFFICIENT", "unobservable transport field needs a reason")
    elif pair["unavailable_reason"] is not None:
        fail("OBSERVATION_PROFILE_INSUFFICIENT", "observed transport field cannot also be unavailable")


def _semantics(kind: str, data: dict) -> None:
    from video_paper_wiki_research.arxiv_preview import normalize_arxiv, validate_origin_url

    for key in ("observed_at", "published_at", "updated_at", "generated_at"):
        if key in data:
            timestamp(data[key])
    if kind == "request":
        entity, version = normalize_arxiv(data["source_url"])
        if (entity != data["entity_id"] or version != data["requested_version"]
                or data["source_url"] != "https://arxiv.org/abs/" + entity + (f"v{version}" if version else "")
                or data["resolution_policy"] != ("explicit" if version else "latest_observation")):
            fail("CONNECTOR_REQUEST_INVALID", "request does not bind canonical arXiv identity and policy")
    elif kind == "observation":
        _ref_kind(data["request"], "request")
        _identity(data["executor"])
        validate_origin_url(data["source_url"])
        transport = data["transport"]
        for pair in transport.values():
            _pair(pair)
        if transport["final_url"]["value"] is not None:
            validate_origin_url(transport["final_url"]["value"])
        for url in transport["redirect_chain"]["value"] or []:
            validate_origin_url(url)
        for address in transport["dns_ips"]["value"] or []:
            try:
                ipaddress.ip_address(address)
            except ValueError:
                fail("OBSERVATION_PROFILE_INSUFFICIENT", "observed IP address is invalid")
        payload = data["payload"]
        if data["outcome"]["status"] == "ok" and payload is None:
            fail("OBSERVATION_MISSING", "successful observation requires a payload")
        if data["capability_profile"] == "normalized-content":
            if transport["raw_response_sha256"]["value"] is not None:
                fail("OBSERVATION_PROFILE_INSUFFICIENT", "normalized content cannot claim a raw response hash")
            if payload is not None:
                if payload["format"] != "arxiv-abs-normalized-text-v1" or payload["sha256"] != sha(payload["text"].encode("utf-8")):
                    fail("OBSERVATION_BINDING_MISMATCH", "normalized payload format or hash differs")
        else:
            if payload is None or payload["format"] != "raw-response-reference-v1":
                fail("OBSERVATION_PROFILE_INSUFFICIENT", "byte-exact profile requires a raw reference")
            if any(transport[k]["value"] is None for k in ("final_url", "redirect_chain", "content_type", "raw_response_sha256")):
                fail("OBSERVATION_PROFILE_INSUFFICIENT", "byte-exact reference lacks required transport observations")
            if (transport["raw_response_sha256"]["value"] != payload["sha256"]
                    or payload["path"].startswith("/") or any(p in {"", ".", ".."} for p in payload["path"].split("/"))
                    or "\\" in payload["path"]):
                fail("OBSERVATION_BINDING_MISMATCH", "raw reference hash or confined path differs")
    elif kind in {"metadata", "preview"}:
        entity, version = normalize_arxiv(data["entity_id"])
        if entity != data["entity_id"] or version is not None:
            fail("ARXIV_ID_INVALID", "metadata entity must be canonical and unversioned")
        if data["requested_version"] is not None and data["requested_version"] != data["resolved_version"]:
            fail("ARXIV_VERSION_MISMATCH", "explicit requested and resolved versions differ")
        if kind == "metadata":
            _ref_kind(data["request"], "request")
            _ref_kind(data["observation"], "observation")
            for value in [data["title"], data["abstract"], *data["authors"], *data["categories"]]:
                if not value.strip():
                    fail("ARXIV_METADATA_INCOMPLETE", "bibliographic fields must contain text")
            suffix = entity + f'v{data["resolved_version"]}'
            if data["abstract_url"] != "https://arxiv.org/abs/" + suffix or data["pdf_url"] != "https://arxiv.org/pdf/" + suffix:
                fail("ARXIV_VERSION_MISMATCH", "metadata links must bind the resolved version")
            if timestamp(data["published_at"]) > timestamp(data["updated_at"]):
                fail("ARXIV_METADATA_INCOMPLETE", "publication and version timestamps are inconsistent")
        else:
            _ref_kind(data["metadata"], "metadata")
            _identity(data["generator"]["model"])
            _identity(data["generator"]["runtime"])
            if any(not section["text"].strip() for section in data["sections"].values()):
                fail("PREVIEW_PROPOSAL_INVALID", "preview sections must contain text")
    elif kind == "decision":
        _ref_kind(data["preview"], "preview")
        previous = data["previous"]
        if (data["sequence"] == 1) != (previous is None):
            fail("DECISION_INVALID", "decision sequence and predecessor disagree")
        if previous is not None:
            _ref_kind(previous, "decision")
        if (data["action"] == "ingest") != (data["selected_version"] is not None):
            fail("DECISION_INVALID", "only an explicit ingest choice selects a version")
        if not data["user_record"]["text"].strip():
            fail("DECISION_INVALID", "decision must record nonempty user or fixture text")
        timestamp(data["user_record"]["recorded_at"])


def seal(kind: str, data: object) -> dict:
    if type(kind) is not str or kind not in KINDS:
        fail("ARTIFACT_INVALID", "unknown preview kind")
    preflight(data)
    body = {"schema_version": KINDS[kind], "kind": kind, "data": copy.deepcopy(data)}
    content_sha = sha(canonicalize(body))
    document = {**body, "content_sha256": content_sha, "id": f"rw1:{kind}:{content_sha}"}
    return validate(document, kind)


def validate(document: object, expected_kind: str | None = None) -> dict:
    preflight(document)
    if type(document) is not dict or type(document.get("kind")) is not str or document["kind"] not in KINDS:
        fail("ARTIFACT_INVALID", "input is not a preview artifact")
    kind = document["kind"]
    if expected_kind is not None and kind != expected_kind:
        fail("ARTIFACT_BINDING_MISMATCH", "artifact has the wrong kind")
    validate_shape(document, KINDS[kind])
    body = {key: document[key] for key in ("schema_version", "kind", "data")}
    content_sha = sha(canonicalize(body))
    if document["content_sha256"] != content_sha or document["id"] != f"rw1:{kind}:{content_sha}":
        fail("ARTIFACT_BINDING_MISMATCH", "artifact identity does not bind its content")
    _semantics(kind, document["data"])
    saved_bytes(document)
    return copy.deepcopy(document)


def task_prompt(metadata: dict) -> bytes:
    validate(metadata, "metadata")
    return resource_bytes("paper-preview-v1.md") + b"\n" + saved_bytes(metadata)


def validate_proposal(document: object) -> dict:
    preflight(document, code="PREVIEW_PROPOSAL_INVALID")
    reg, schemas = registry()
    common_id = schemas[PREFIX + "preview-common.v1"]["$id"]
    fields = {"generator": "generator", "generated_at": "utc_timestamp", "prompt_sha256": "sha256", "sections": "sections"}
    schema = {"type": "object", "additionalProperties": False, "required": list(fields),
              "properties": {key: {"$ref": common_id + "#/$defs/" + stem} for key, stem in fields.items()}}
    error = next(_Validator(schema, registry=reg).iter_errors(document), None)
    if error is not None:
        fail("PREVIEW_PROPOSAL_INVALID", "proposal must contain valid generator, time, task hash and six sections",
             pointer="/" + "/".join(str(p) for p in error.absolute_path), keyword=error.validator)
    _identity(document["generator"]["model"])
    _identity(document["generator"]["runtime"])
    timestamp(document["generated_at"])
    if any(not section["text"].strip() for section in document["sections"].values()):
        fail("PREVIEW_PROPOSAL_INVALID", "preview sections must contain text")
    return copy.deepcopy(document)


def validate_graph(document: dict, resolve, *, seen: set[str] | None = None, memo: dict | None = None) -> dict:
    """Resolve every reference, then rederive metadata and preview bindings."""
    value = validate(document)
    cache = {} if memo is None else memo
    key = reference(value)["sha256"]
    if key in cache:
        return cache[key]
    active = set() if seen is None else set(seen)
    if value["id"] in active or len(active) > 260:
        fail("ARTIFACT_BINDING_MISMATCH", "artifact graph is cyclic or too deep")
    active.add(value["id"])
    data, kind = value["data"], value["kind"]

    def linked(ref, expected):
        child = resolve(ref, expected)
        if reference(child) != ref:
            fail("ARTIFACT_BINDING_MISMATCH", "linked artifact bytes differ from reference")
        return validate_graph(child, resolve, seen=active, memo=cache)

    if kind == "observation":
        request = linked(data["request"], "request")
        if data["source_url"] != request["data"]["source_url"]:
            fail("OBSERVATION_BINDING_MISMATCH", "observation URL differs from its request")
    elif kind == "metadata":
        request = linked(data["request"], "request")
        observation = linked(data["observation"], "observation")
        from video_paper_wiki_research.arxiv_preview import derive_metadata
        if derive_metadata(request, observation) != data:
            fail("ARTIFACT_BINDING_MISMATCH", "metadata is not derived from the referenced page observation")
    elif kind == "preview":
        metadata = linked(data["metadata"], "metadata")
        if any(data[key] != metadata["data"][key] for key in VERSION_FIELDS) or data["prompt_sha256"] != sha(task_prompt(metadata)):
            fail("PREVIEW_SCOPE_INVALID", "preview version, time or prompt differs from its metadata")
    elif kind == "decision":
        preview = linked(data["preview"], "preview")
        if data["action"] == "ingest" and data["selected_version"] != preview["data"]["resolved_version"]:
            fail("DECISION_INVALID", "selected version differs from the preview")
        if data["previous"] is not None:
            previous = linked(data["previous"], "decision")
            if previous["data"]["sequence"] + 1 != data["sequence"]:
                fail("DECISION_INVALID", "decision predecessor sequence differs")
    cache[key] = value
    return value
