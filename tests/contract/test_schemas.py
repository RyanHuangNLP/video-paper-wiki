from __future__ import annotations

import copy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from video_paper_wiki.contracts import ContractError, schema_by_title, validate_document
import video_paper_wiki.resources as resource_module

from .paths import VALID, load_json


def _fixture_for(schema: dict) -> Path:
    return VALID / f"{schema['title']}.json"


def _first_nested_object(document: dict) -> dict | None:
    for value in document.values():
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    return item
    return None


def test_all_schemas_are_draft_2020_12_and_well_formed(schema_paths: list[Path]) -> None:
    assert len(schema_paths) == 69
    for path in schema_paths:
        schema = load_json(path)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"] == f"https://video-paper-wiki.dev/schemas/{path.name}"
        assert schema["title"] == path.name.removesuffix(".schema.json")
        Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("title", [
    "video-paper-wiki.projection-input.v1",
    "video-paper-wiki.projection-generation.v1",
    "video-paper-wiki.catalog-rows.v1",
])
def test_projection_schema_titles_are_in_offline_registry(title: str) -> None:
    schema = schema_by_title(title)
    assert schema["title"] == title


def test_projection_resources_reject_installed_ancestor_decoys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    installed=tmp_path/"decoy"/"site-packages"/"video_paper_wiki"
    installed.mkdir(parents=True); fake=installed/"resources.py"; fake.write_text("",encoding="utf-8")
    (tmp_path/"decoy"/"catalog").mkdir(); (tmp_path/"decoy"/"catalog"/"x").write_bytes(b"decoy")
    (tmp_path/"decoy"/"schemas").mkdir(); (tmp_path/"decoy"/"schemas"/"x.schema.json").write_text("{}")
    empty=tmp_path/"empty-package"; empty.mkdir()
    monkeypatch.setattr(resource_module,"__file__",str(fake))
    monkeypatch.setattr(resource_module.resources,"files",lambda _package: empty)
    assert resource_module.read_projection_resource_bytes("catalog","x") is None
    assert resource_module.load_schema_json("x.schema.json") is None
    assert resource_module.schema_resource_names()==()


def test_projection_resources_allow_only_exact_source_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root=tmp_path/"repo"; module=root/"src/video_paper_wiki/resources.py"
    module.parent.mkdir(parents=True); module.write_text("",encoding="utf-8")
    (root/"catalog").mkdir(); (root/"catalog"/"x").write_bytes(b"catalog")
    (root/"schemas").mkdir(); (root/"schemas"/"x.schema.json").write_text('{"title":"x"}')
    empty=tmp_path/"empty-package"; empty.mkdir()
    monkeypatch.setattr(resource_module,"__file__",str(module))
    monkeypatch.setattr(resource_module.resources,"files",lambda _package: empty)
    assert resource_module.read_projection_resource_bytes("catalog","x")==b"catalog"
    assert resource_module.load_schema_json("x.schema.json")=={"title":"x"}
    assert resource_module.schema_resource_names()==("x.schema.json",)


def test_projection_generation_ref_resolves_offline() -> None:
    schema = schema_by_title("video-paper-wiki.projection-generation.v1")
    assert schema["properties"]["inventory"]["$ref"].endswith(
        "video-paper-wiki.projection-input.v1.schema.json"
    )
    h="a"*64
    inventory={"schema":"video-paper-wiki.projection-input.v1","entries":[
        {"path":"taxonomy/v1.json","kind":"taxonomy","sha256":h,"size_bytes":0},
        {"path":"wiki/meta/ledgers/claim-ledger.json","kind":"claim-ledger","sha256":h,"size_bytes":0},
        {"path":"wiki/meta/ledgers/source-ledger.json","kind":"source-ledger","sha256":h,"size_bytes":0}]}
    item={"path":"x","sha256":h}
    generation={"schema":"video-paper-wiki.projection-generation.v1","profile":"base-catalog-v1","inventory":inventory,
        "implementation":{"package_version":"0.1.0","files":[item]},"resources":{"files":[item]},
        "dependencies":{"profile":"vpwiki-jsonschema-date-utc-v1","distributions":[{"name":"attrs","version":"26.1.0"}]},
        "upstream":{"commit":"9f8c1199047eac2c3828496279fbb7ba9540b90b","version":"2.1.1","files":[item]},
        "runtime":{"python_implementation":"CPython","python_version":"3.13.13","unicode_version":"15.1.0","prefix_mode":"synthetic","chunk_profile":"claude-obsidian.chunk.v1","bm25_profile":"claude-obsidian.bm25.v2"}}
    validate_document(inventory,expected_schema="video-paper-wiki.projection-input.v1")
    validate_document(generation,expected_schema="video-paper-wiki.projection-generation.v1")
    validate_document({"schema":"video-paper-wiki.catalog-rows.v1","ddl_sha256":h,"generation_sha256":h,
                       "tables":[{"name":"x","columns":["x"],"rows":[[None]]}]},expected_schema="video-paper-wiki.catalog-rows.v1")


def test_projection_schema_patterns_reject_all_terminal_line_separators() -> None:
    def patterns(value):
        if isinstance(value, dict):
            if isinstance(value.get("pattern"), str):
                yield value["pattern"]
            for child in value.values():
                yield from patterns(child)
        elif isinstance(value, list):
            for child in value:
                yield from patterns(child)

    schemas = [schema_by_title(title) for title in (
        "video-paper-wiki.projection-input.v1",
        "video-paper-wiki.projection-generation.v1",
        "video-paper-wiki.catalog-rows.v1",
    )]
    def sample(pattern: str) -> str:
        choices = (
            ("source-ledger", "wiki/meta/ledgers/source-ledger.json"),
            ("claim-ledger", "wiki/meta/ledgers/claim-ledger.json"),
            ("taxonomy/v1", "taxonomy/v1.json"),
            ("records/papers", "wiki/meta/records/papers/p.json"),
            ("records/repos", "wiki/meta/records/repos/r.json"),
            ("meta/reviews", "wiki/meta/reviews/clm-" + "a" * 20 + "/ase-" + "b" * 20 + ".json"),
            ("raw/captured", ".raw/captured/" + "a" * 64 + ".pdf"),
            ("parser-config", ".raw/derived/" + "a" * 64 + "/docling/" + "b" * 64 + "/parser-config.json"),
            ("model-manifest", ".raw/derived/" + "a" * 64 + "/docling/" + "b" * 64 + "/model-manifest.json"),
            ("/docling/", ".raw/derived/" + "a" * 64 + "/docling/" + "b" * 64 + "/document.json"),
            ("/runs/", ".raw/derived/" + "a" * 64 + "/runs/run-1.json"),
            ("code-manifests", ".raw/derived/code-manifests/" + "a" * 64 + ".json"),
            ("alignment-manifests", ".raw/derived/alignment-manifests/" + "a" * 64 + ".json"),
        )
        for marker, value in choices:
            if marker in pattern:
                return value
        if "[0-9a-f]{64}" in pattern: return "a" * 64
        if "[\\x21-\\x7e]" in pattern: return "x"
        if "[a-z0-9]+(?:-[a-z0-9]+)*" in pattern: return "attrs"
        if "[0-9A-Za-z][0-9A-Za-z.+!-]*" in pattern: return "26.1.0"
        if "[a-z][a-z0-9_]*" in pattern: return "table_1"
        raise AssertionError(pattern)
    found = list(patterns(schemas))
    assert len(found) == 38
    for pattern in found:
        assert pattern.endswith("$(?![\\s\\S])")
        validator = Draft202012Validator({"type": "string", "pattern": pattern})
        value = sample(pattern)
        assert validator.is_valid(value)
        for suffix in ("\n", "\r", "\r\n", "\u2028", "\u2029"):
            assert not validator.is_valid(value + suffix)


@pytest.mark.parametrize("schema_name", [
    "video-paper-wiki.transaction-facade.v1", "video-paper-wiki.operation-head.v1",
    "video-paper-wiki.upstream-authority.v1", "video-paper-wiki.upstream-capture-authority.v1",
    "video-paper-wiki.transaction-staging.v1",
    "video-paper-wiki.staged-pdf-capture-request.v1",
    "video-paper-wiki.staged-pdf-capture-authority.v1",
    "video-paper-wiki.capture-inspection.v1", "video-paper-wiki.code-evidence-manifest.v1",
    "video-paper-wiki.ingest-plan.v1", "video-paper-wiki.prepared.v1",
    "video-paper-wiki.paper-analysis-draft.v1", "video-paper-wiki.paper-code-alignment.v1",
    "video-paper-wiki.paper-record.v1", "video-paper-wiki.repo-record.v1",
    "video-paper-wiki.assessment-event.v1", "video-paper-wiki.gate-decision.v1",
    "video-paper-wiki.operation-receipt.v1", "video-paper-wiki.run-manifest.v1",
])
def test_domain_valid_fixture_and_closed_top_level(schema_name: str) -> None:
    schema = load_json(Path("schemas") / f"{schema_name}.schema.json")
    document = load_json(_fixture_for(schema))
    validate_document(document, expected_schema=schema_name)
    invalid = copy.deepcopy(document)
    invalid["unexpected_field"] = true_value = True
    assert true_value
    with pytest.raises(ContractError) as exc:
        validate_document(invalid, expected_schema=schema_name)
    assert exc.value.code == "SCHEMA_INVALID"


@pytest.mark.parametrize("schema_name", [
    "video-paper-wiki.transaction-facade.v1",
    "video-paper-wiki.upstream-authority.v1", "video-paper-wiki.upstream-capture-authority.v1",
    "video-paper-wiki.transaction-staging.v1",
    "video-paper-wiki.staged-pdf-capture-request.v1",
    "video-paper-wiki.staged-pdf-capture-authority.v1",
    "video-paper-wiki.capture-inspection.v1", "video-paper-wiki.code-evidence-manifest.v1",
    "video-paper-wiki.ingest-plan.v1", "video-paper-wiki.prepared.v1",
    "video-paper-wiki.paper-analysis-draft.v1", "video-paper-wiki.paper-code-alignment.v1",
    "video-paper-wiki.paper-record.v1", "video-paper-wiki.repo-record.v1",
    "video-paper-wiki.operation-receipt.v1", "video-paper-wiki.run-manifest.v1",
])
def test_nested_objects_reject_extra_fields(schema_name: str) -> None:
    schema = load_json(Path("schemas") / f"{schema_name}.schema.json")
    invalid = copy.deepcopy(load_json(_fixture_for(schema)))
    nested = _first_nested_object(invalid)
    assert nested is not None
    nested["unexpected_field"] = True
    with pytest.raises(ContractError) as exc:
        validate_document(invalid, expected_schema=schema_name)
    assert exc.value.code == "SCHEMA_INVALID"


@pytest.mark.parametrize("paper_id", ["/tmp", "../", "   ", "a\n.."])
def test_paper_analysis_draft_paper_id_rejects_path_segments(paper_id: str) -> None:
    schema = load_json(Path("schemas") / "video-paper-wiki.paper-analysis-draft.v1.schema.json")
    document = copy.deepcopy(load_json(_fixture_for(schema)))
    validate_document(document, expected_schema="video-paper-wiki.paper-analysis-draft.v1")
    document["paper_id"] = paper_id
    document["claims"] = []
    with pytest.raises(ContractError) as exc:
        validate_document(document, expected_schema="video-paper-wiki.paper-analysis-draft.v1")
    assert exc.value.code in {"SCHEMA_INVALID", "INVALID_PAPER_ID"}


def test_paper_analysis_draft_paper_id_accepts_canonical_id_not_page_slug() -> None:
    schema = load_json(Path("schemas") / "video-paper-wiki.paper-analysis-draft.v1.schema.json")
    document = copy.deepcopy(load_json(_fixture_for(schema)))
    document["claims"] = []
    document["paper_id"] = "arxiv:2209.14792"
    validate_document(document, expected_schema="video-paper-wiki.paper-analysis-draft.v1")
    document["paper_id"] = "arxiv-2209.14792"
    with pytest.raises(ContractError) as exc:
        validate_document(document, expected_schema="video-paper-wiki.paper-analysis-draft.v1")
    assert exc.value.code in {"SCHEMA_INVALID", "INVALID_PAPER_ID"}
