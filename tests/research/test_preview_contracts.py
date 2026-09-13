import copy
import json

import pytest

from tests.preview_fixture import observation
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.paper_preview import make_request
from video_paper_wiki_research.preview_contracts import (
    SCHEMA_FILES, parse_json, reference, resource_bytes, saved_bytes, seal, sha, validate, validate_graph, validate_shape,
)


def test_identity_content_hash_distinct_from_file_hash():
    request = make_request("2408.06072v2")
    assert validate(request) == request
    assert reference(request)["sha256"] == sha(saved_bytes(request))
    assert reference(request)["sha256"] != request["content_sha256"]
    assert make_request("https://arxiv.org/abs/2408.06072v2") == request
    assert make_request("2408.06072") != request
    assert len(SCHEMA_FILES) == 7 and all(json.loads(resource_bytes(name)) for name in SCHEMA_FILES)


@pytest.mark.parametrize("bad", [None, [], {"kind": []}, {"kind": {}}, {"kind": True}])
def test_unhashable_kind_refuses(bad):
    with pytest.raises(ResearchError):
        validate(bad)


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'{"a":1.5}',
                                    b'"\\ud800"', b'\xff', b'[' * 34 + b'0' + b']' * 34])
def test_strict_json(raw):
    with pytest.raises(Exception) as caught:
        parse_json(raw)
    assert hasattr(caught.value, "code")


@pytest.mark.parametrize("change", [
    lambda value: value.update(extra=True),
    lambda value: value["data"]["budget"].update(max_requests=True),
    lambda value: value["data"].update(requested_version=0),
    lambda value: value.update(content_sha256="0" * 64),
    lambda value: value.update(kind="metadata"),
])
def test_closed_request_shape_and_hash(change):
    value = make_request("2408.06072v2")
    change(value)
    with pytest.raises(ResearchError):
        validate(value)


@pytest.mark.parametrize("change", [
    lambda data: data["transport"]["raw_response_sha256"].update(value="a" * 64, unavailable_reason=None),
    lambda data: data["transport"]["headers"].update(unavailable_reason=""),
    lambda data: data["transport"]["final_url"].update(value="https://arxiv.org.evil/abs/2408.06072", unavailable_reason=None),
    lambda data: data["transport"]["wire_bytes"].update(value=1048577, unavailable_reason=None),
    lambda data: data["transport"]["redirect_chain"].update(value=["https://arxiv.org"] * 3, unavailable_reason=None),
    lambda data: data["payload"].update(sha256="0" * 64),
    lambda data: data["executor"].update(value="invented"),
])
def test_observation_refusals(change):
    data = observation()
    change(data)
    with pytest.raises(ResearchError):
        seal("observation", data)


def test_request_binding_requires_resolved_graph():
    request = make_request("2408.06072v2")
    data = observation(request)
    data["source_url"] = "https://arxiv.org/abs/2408.06073v2"
    value = seal("observation", data)
    with pytest.raises(ResearchError) as caught:
        validate_graph(value, lambda ref, kind: request)
    assert caught.value.code == "OBSERVATION_BINDING_MISMATCH"


def test_raw_reference_closed_branch():
    data = observation()
    data["capability_profile"] = "byte-exact"
    data["payload"] = {"format": "raw-response-reference-v1", "path": "future/raw.bin", "sha256": "a" * 64,
                       "bytes": 100, "executor_receipt_sha256": "b" * 64}
    for key, value in {"final_url": data["source_url"], "redirect_chain": [], "content_type": "text/html",
                       "raw_response_sha256": "a" * 64}.items():
        data["transport"][key] = {"value": value, "unavailable_reason": None}
    assert seal("observation", data)["data"] == data
    bad = copy.deepcopy(data)
    bad["payload"]["path"] = "../raw.bin"
    with pytest.raises(ResearchError):
        seal("observation", bad)


def test_skill_manifest_binds_installed_entrypoint():
    from pathlib import Path
    root = Path(__file__).parents[2] / ".agents/skills/video-paper-preview"
    manifest = json.loads((root / "skill-contract.v1.json").read_bytes())
    validate_shape(manifest, "skill-contract.v1")
    assert manifest["skill_md_sha256"] == sha((root / "SKILL.md").read_bytes())
    assert len(manifest["commands"]) == 7
