from __future__ import annotations

import copy
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tests.contract.test_capture_contracts import inspected
from video_paper_wiki.code_evidence_contracts import code_snippet_sha256
from video_paper_wiki.contracts import ContractError, _registry, _validator_for, schema_by_title
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.resources import _RESOURCE_VIEW, _retained_resource_view, load_schema_json, read_projection_resource_bytes, read_schema_text, schema_resource_names
from video_paper_wiki.source_catalog import query_source_catalog, resolve_source_catalog
from video_paper_wiki.source_catalog_projection import _code_resolution, _pdf_resolution, _pointer
from video_paper_wiki.source_catalog_query import query_parameters, search, tokens
from video_paper_wiki.source_semantics_contracts import sha


@pytest.mark.parametrize("text,expected", [
    ("ＡＢＣ １２3", ["abc", "123"]), ("时序注意力", ["时", "序", "注", "意", "力", "时序", "序注", "注意", "意力"]),
    ("时序，注意", ["时", "序", "时序", "注", "意", "注意"]),
    ("résumé STRAẞE Ελληνικά", ["r", "é", "sum", "é", "strasse", "ελληνικά"]),
    ("𠀀𠀁abc中a", ["𠀀", "𠀁", "𠀀𠀁", "abc", "中", "a"]),
    ("yes yes", ["yes", "yes"]), ("e\u0301", ["é"]), ("---", []),
])
def test_frozen_tokenizer(text, expected):
    assert tokens(text) == expected


@pytest.mark.parametrize("overrides,code", [
    ({"text": ""}, "SOURCE_CATALOG_INVALID"), ({"text": "!?"}, "SOURCE_CATALOG_INVALID"),
    ({"text": "\ud800"}, "SOURCE_CATALOG_INVALID"), ({"text": "a" * 513}, "SOURCE_CATALOG_LIMIT"),
    ({"text": "ﬃ" * 171}, "SOURCE_CATALOG_LIMIT"), ({"text": "ß" * 257}, "SOURCE_CATALOG_LIMIT"),
    ({"text": "中" * 501}, "SOURCE_CATALOG_LIMIT"), ({"limit": True}, "SOURCE_CATALOG_INVALID"),
    ({"limit": 0}, "SOURCE_CATALOG_LIMIT"), ({"limit": 1001}, "SOURCE_CATALOG_LIMIT"),
    ({"offset": -1}, "SOURCE_CATALOG_LIMIT"), ({"offset": 1000001}, "SOURCE_CATALOG_LIMIT"),
    ({"offset": 0.0}, "SOURCE_CATALOG_INVALID"), ({"scope": "raw"}, "SOURCE_CATALOG_INVALID"),
    ({"assessment": "approved"}, "SOURCE_CATALOG_INVALID"), ({"lifecycle": None}, "SOURCE_CATALOG_INVALID"),
    ({"paper_id": "not-an-id"}, "SOURCE_CATALOG_INVALID"), ({"catalog_sha256": "bad"}, "SOURCE_CATALOG_INVALID"),
])
def test_bad_queries_refuse_before_io(monkeypatch, overrides, code):
    import video_paper_wiki.source_catalog as module
    monkeypatch.setattr(module, "catalog_slot", lambda *a, **k: pytest.fail("input error performed IO"))
    with pytest.raises(ContractError) as err:
        query_source_catalog(vault_root="missing", batch_id="x", **{"text": "valid", **overrides})
    assert err.value.code == code and "instance_pointer" in err.value.details
    assert err.value.exit_code == (75 if code.endswith("LIMIT") else 2)


@pytest.mark.parametrize("ordinal", [True, False, 1.0, "1", None])
def test_resolve_ordinal_is_not_coerced(monkeypatch, ordinal):
    import video_paper_wiki.source_catalog as module
    monkeypatch.setattr(module, "catalog_slot", lambda *a, **k: pytest.fail("invalid ordinal performed IO"))
    with pytest.raises(ContractError) as err:
        resolve_source_catalog(vault_root="missing", batch_id="x", claim_id="clm-" + "a" * 20, evidence_ordinal=ordinal)
    assert err.value.code == "SOURCE_CATALOG_INVALID"


@pytest.mark.parametrize("assessment", ["accepted", "provisional", "contested", "unsupported", "deprecated"])
@pytest.mark.parametrize("lifecycle", ["active", "retired"])
def test_all_history_states_filter_claim_and_excerpt_together(assessment, lifecycle):
    claim = {"claim_id": "clm-a", "owner_kind": "paper", "owner_id": "arxiv:2609.00001", "text": "时序注意力",
             "assessment": assessment, "reference": {"lifecycle": lifecycle}}
    evidence = {"claim_id": "clm-a", "source_id": "src-a", "association_id": "cited",
                "display_association_id": "display", "ordinal": 0,
                "resolution": {"state": "RESOLVED", "excerpt": "时序注意力"}}
    rows = {"repositories": [], "claims": [claim], "evidence": [evidence]}
    kwargs = dict(scope="all", paper_id="arxiv:2609.00001", assessment=assessment, lifecycle=lifecycle, limit=20, offset=0)
    result = search(rows, Counter(tokens("时序注意力")), **kwargs)
    assert [x["kind"] for x in result["hits"]] == ["claims", "source_excerpts"]
    assert all(x["score"] == 1000000 and x["assessment"] == assessment and x["lifecycle"] == lifecycle for x in result["hits"])
    assert result["hits"][1]["association_id"] == "cited" and result["hits"][1]["display_association_id"] == "display"
    assert search(rows, Counter(tokens("时序注意力")), **{**kwargs, "lifecycle": "retired" if lifecycle == "active" else "active"})["hits"] == []


def test_multiset_dice_ordering_paging_and_explicit_repo_paper_filter():
    claims = [{"claim_id": "clm-" + s, "owner_kind": "repo", "owner_id": "github:owner/repo",
               "text": t, "assessment": "provisional", "reference": {"lifecycle": "active"}}
              for s, t in [("b", "yes yes no"), ("a", "yes no"), ("c", "yes yes no")]]
    rows = {"repositories": [{"repo_id": "github:owner/repo", "paper_ids": ["arxiv:2609.00001"]}], "claims": claims, "evidence": []}
    kwargs = dict(scope="all", paper_id="arxiv:2609.00001", assessment="all", lifecycle="active", limit=1, offset=0)
    query = Counter(tokens("yes yes"))
    first = search(rows, query, **kwargs)
    assert first["hits"][0]["claim_id"] == "clm-b" and first["hits"][0]["score"] == 800000
    assert first["next_offset"] == 1 and first["total_matches"] == 3
    assert search(rows, query, **{**kwargs, "offset": 1})["hits"][0]["claim_id"] == "clm-c"
    assert search(rows, query, **{**kwargs, "offset": 2})["hits"][0]["score"] == 500000
    assert search(rows, query, **{**kwargs, "paper_id": "arxiv:2609.99999"})["hits"] == []


def pdf_material(text="时序e\u0301\r\nattention", *, span=None):
    span = [0, len(text)] if span is None else span
    raw = json.dumps({"texts": [{"text": text, "prov": [{"page_no": 2, "bbox": [1.5, 2.5, 3.5, 4.5]}]}]}, ensure_ascii=False).encode()
    path = ".raw/derived/" + "a" * 64 + "/docling/fp/document.json"
    loc = {"kind": "pdf", "source_id": "src-a", "page": 2, "ref": "#/texts/0",
           "artifact_path": path, "artifact_sha256": sha(raw), "charspan": span,
           "text_sha256": sha(text[span[0]:span[1]].encode())}
    return loc, {path: raw}, text


def test_pdf_resolution_keeps_exact_unicode_and_contextual_bbox():
    loc, data, text = pdf_material()
    result = _pdf_resolution(loc, data)
    assert result["state"] == "RESOLVED" and result["excerpt"] == text
    assert result["excerpt_sha256"] == sha(text.encode())
    assert result["position"] == {"kind": "pdf", "page": 2, "ref": "#/texts/0", "charspan": [0, len(text)]}
    assert _pointer({"a/b": {"~c": ["found"]}}, "#/a~1b/~0c/0") == "found"
    assert _pointer({"汉": "found"}, "#/%E6%B1%89") == "found"


@pytest.mark.parametrize("change,reason", [("pointer", "legacy_json_pointer_unavailable"), ("object", "legacy_object_not_text"),
    ("page", "legacy_page_not_reconstructable"), ("span", "legacy_charspan_unavailable"), ("large", "excerpt_limit")])
def test_legacy_unreconstructable_excerpt_has_explicit_reason(change, reason):
    loc, data, _ = pdf_material("x" * 65537 if change == "large" else "text")
    if change == "pointer": loc["ref"] = "#/texts/01"
    if change == "object": loc["ref"] = "#/texts"
    if change == "page": loc["page"] = 3
    if change == "span": del loc["charspan"]
    result = _pdf_resolution(loc, data)
    assert result["state"] == "UNSUPPORTED_LEGACY_RESOLUTION" and result["reason"] == reason
    assert result["excerpt"] is result["excerpt_sha256"] is None


@pytest.mark.parametrize("field,value", [("charspan", [0, 999]), ("charspan", [1, 0]), ("charspan", [0, 0]),
    ("charspan", [True, 2]), ("text_sha256", "f" * 64), ("artifact_sha256", "f" * 64)])
def test_present_invalid_pdf_span_or_hash_refuses(field, value):
    loc, data, _ = pdf_material()
    loc[field] = value
    with pytest.raises(ContractError) as err:
        _pdf_resolution(loc, data)
    assert err.value.code == "SOURCE_CATALOG_EVIDENCE_INVALID" and err.value.exit_code == 75


@pytest.mark.parametrize("raw,start,end,expected", [(b"a\r\nb\n", 1, 2, "a\nb"), (b"a\nb", 2, 2, "b"),
    ("汉\n字\n".encode(), 1, 1, "汉"), (b"a\n\nb\n", 2, 3, "\nb")])
def test_code_resolution_uses_the_established_normalized_line_slice(raw, start, end, expected):
    manifest, _ = inspected(raw)
    loc = {"kind": "code", "source_id": manifest["capture"]["source_id"], **manifest["origin"],
           "lines": {"start": start, "end": end}, "snippet_sha256": code_snippet_sha256(raw, start, end)}
    result = _code_resolution(loc, {"code-evidence-manifest": {"manifest": manifest}}, {manifest["capture"]["stored_path"]: raw})
    assert result["excerpt"] == expected and result["excerpt_sha256"] == loc["snippet_sha256"]


def resource_material(word):
    root = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "https://test.invalid/main", "title": "test.resource-view",
            "type": "object", "properties": {"word": {"$ref": "https://test.invalid/word"}}, "required": ["word"]}
    leaf = {"$schema": root["$schema"], "$id": "https://test.invalid/word", "title": "test.word", "const": word}
    return {("schema", "main.schema.json"): json.dumps(root).encode(), ("schema", "word.schema.json"): json.dumps(leaf).encode(),
            ("taxonomy", "v1.json"): word.encode()}


def test_private_resource_view_transitive_refs_nested_exception_and_default_cache():
    from video_paper_wiki.projection_catalog import _closed_schema
    from video_paper_wiki.projection_generation import _registry as direct_registry
    ordinary = _registry()
    schema = copy.deepcopy(schema_by_title("video-paper-wiki.common.v1"))
    material = resource_material("outer")
    names = ("main.schema.json", "word.schema.json")
    with _retained_resource_view(material, names) as outer:
        material[("taxonomy", "v1.json")] = b"mutated caller mapping"
        assert read_projection_resource_bytes("taxonomy", "v1.json") == b"outer"
        assert read_projection_resource_bytes("catalog", "missing.json") is None
        assert read_schema_text("video-paper-wiki.common.v1.schema.json") is None
        assert schema_resource_names() == names and load_schema_json("missing.schema.json") is None
        _closed_schema({"word": "outer"}, "test.resource-view", "")
        assert direct_registry()[1] == _registry()[1] and _registry() is not ordinary
        assert not _validator_for(schema_by_title("test.resource-view")).is_valid({"word": "inner"})
        with pytest.raises(ContractError):
            with _retained_resource_view(resource_material("inner"), names) as inner:
                _closed_schema({"word": "inner"}, "test.resource-view", "")
                assert inner is not outer
                _closed_schema({"word": "outer"}, "test.resource-view", "")
        assert _RESOURCE_VIEW.get() is outer and read_projection_resource_bytes("taxonomy", "v1.json") == b"outer"
        _closed_schema({"word": "outer"}, "test.resource-view", "")
    assert _RESOURCE_VIEW.get() is None and _registry() is ordinary
    assert schema_by_title("video-paper-wiki.common.v1") == schema


def test_independent_resource_contexts_have_independent_registries():
    from threading import Barrier
    barrier = Barrier(2)
    def run(word):
        with _retained_resource_view(resource_material(word), ("main.schema.json", "word.schema.json")):
            registry = _registry()
            barrier.wait(timeout=5)
            validator = _validator_for(schema_by_title("test.resource-view"))
            assert validator.is_valid({"word": word})
            assert not validator.is_valid({"word": "two" if word == "one" else "one"})
            return registry
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = [pool.submit(run, word) for word in ("one", "two")]
        assert a.result(timeout=10) is not b.result(timeout=10)


def test_copied_contexts_share_only_immutable_bytes_not_parsed_schema_objects():
    from contextvars import copy_context
    from dataclasses import FrozenInstanceError
    ordinary = _registry()
    with _retained_resource_view(resource_material("original"), ("main.schema.json", "word.schema.json")) as view:
        parent = _registry()
        copied = copy_context().run(_registry)
        assert parent[0] is not copied[0]
        assert parent[1]["test.word"] is not copied[1]["test.word"]
        copied[1]["test.word"]["const"] = "tampered"
        assert parent[1]["test.word"]["const"] == "original"
        assert _validator_for(schema_by_title("test.resource-view")).is_valid({"word": "original"})
        with pytest.raises(TypeError):
            view.material[("taxonomy", "v1.json")] = b"tampered"
        with pytest.raises(FrozenInstanceError):
            view.schema_names = ()
    assert _registry() is ordinary


def test_public_cli_process_returns_one_envelope_for_every_catalog_leaf(checkout):
    import os
    import subprocess
    import sys
    from tests.upstream.test_source_catalog import published
    from tests.upstream.test_markdown_source import _snapshot
    vault, _, material, _ = published(checkout)
    before = _snapshot(vault)
    paper = material["papers"][0]
    claim_id = paper["claims"][0]["claim_id"]
    package_src = str(Path(__file__).resolve().parents[2] / "src")
    env = {**os.environ, "PYTHONPATH": package_src}
    outputs = {}
    for leaf, flags in [
        ("build", []), ("status", []),
        ("lookup", ["--kind", "paper", "--key", paper["record"]["paper_id"]]),
        ("query", ["--text", "temporal", "--scope", "source_excerpts"]),
        ("resolve", ["--claim-id", claim_id, "--evidence-ordinal", "0"]),
    ]:
        result = subprocess.run(
            [sys.executable, "-m", "video_paper_wiki.cli", "source-catalog", leaf,
             "--vault-root", str(vault), "--batch-id", "cli-catalog", *flags],
            cwd=checkout, env=env, capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, (leaf, result.stdout, result.stderr)
        assert result.stderr == ""
        assert len(result.stdout.splitlines()) == 1
        envelope = json.loads(result.stdout)
        assert set(envelope) == {"ok", "command", "data"}
        assert envelope["ok"] is True
        assert envelope["command"] == "source-catalog." + leaf
        assert envelope["data"]["profile"] == "source-catalog-v1"
        outputs[leaf] = envelope["data"]
    assert outputs["build"]["state"] == "created"
    assert outputs["status"]["state"] == "current"
    assert outputs["lookup"]["matches"][0]["paper_id"] == paper["record"]["paper_id"]
    assert outputs["query"]["hits"][0]["kind"] == "source_excerpts"
    assert outputs["resolve"]["evidence"]["resolution"]["state"] == "RESOLVED"
    assert len({data["catalog_sha256"] for data in outputs.values()}) == 1
    assert _snapshot(vault) == before


@pytest.mark.parametrize("leaf,flags", [
    ("build", []), ("status", []),
    ("lookup", ["--kind", "paper", "--key", "absent"]),
    ("query", ["--text", "temporal"]),
    ("resolve", ["--claim-id", "clm-" + "a" * 20, "--evidence-ordinal", "0"]),
])
def test_cli_invalid_batch_preserves_staging_code_without_touching_paths(tmp_path, capsys, leaf, flags):
    from video_paper_wiki.cli import main
    missing = tmp_path / "not-created"
    status = main(["source-catalog", leaf, "--vault-root", str(missing),
                   "--batch-id", "../bad", *flags])
    captured = capsys.readouterr()
    assert status == 2 and captured.err == ""
    assert len(captured.out.splitlines()) == 1
    envelope = json.loads(captured.out)
    assert envelope["ok"] is False and envelope["command"] == "source-catalog." + leaf
    assert envelope["error"]["code"] == "INVALID_BATCH_ID"
    assert "instance_pointer" in envelope["error"]["details"]
    assert not missing.exists()


@pytest.mark.parametrize("code,exit_code", [("WORK_PATH_UNSAFE", 2), ("STAGING_CONFLICT", 75)])
def test_direct_and_cli_preserve_staging_error_details_and_exit_code(monkeypatch, capsys, code, exit_code):
    import video_paper_wiki.source_catalog as module
    from video_paper_wiki.cli import main
    from video_paper_wiki.staging import StagingError
    def refuse(*args, **kwargs):
        raise StagingError(code, "retained slot refused", {"path": ".work/example"})
    monkeypatch.setattr(module, "validate_batch_id", refuse)
    with pytest.raises(ContractError) as err:
        module.source_catalog_status(vault_root="missing", batch_id="example")
    assert err.value.code == code and err.value.exit_code == exit_code
    assert err.value.details == {"instance_pointer": "", "path": ".work/example"}
    assert main(["source-catalog", "status", "--vault-root", "missing", "--batch-id", "example"]) == exit_code
    captured = capsys.readouterr()
    assert captured.err == "" and len(captured.out.splitlines()) == 1
    assert json.loads(captured.out)["error"] == {
        "code": code, "message": "retained slot refused",
        "details": {"instance_pointer": "", "path": ".work/example"},
    }


def test_cli_preserves_real_catalog_refusal_exit_and_details(checkout, capsys):
    from video_paper_wiki.cli import main
    from tests.upstream.test_source_catalog import published
    from tests.upstream.test_markdown_source import _snapshot
    vault, _, _, _ = published(checkout)
    before = _snapshot(vault)
    status = main(["source-catalog", "query", "--vault-root", str(vault),
                   "--batch-id", "absent-catalog", "--text", "temporal"])
    captured = capsys.readouterr()
    assert status == 75 and captured.err == ""
    assert len(captured.out.splitlines()) == 1
    envelope = json.loads(captured.out)
    assert envelope["ok"] is False and envelope["command"] == "source-catalog.query"
    assert envelope["error"]["code"] == "SOURCE_CATALOG_ABSENT"
    assert "instance_pointer" in envelope["error"]["details"]
    assert not (checkout / ".work/absent-catalog").exists()
    assert _snapshot(vault) == before
