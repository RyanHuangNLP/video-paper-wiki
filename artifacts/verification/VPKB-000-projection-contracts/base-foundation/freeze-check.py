from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[4]
SCHEMAS = ROOT / "schemas"
CATALOG = ROOT / "catalog"
NEW = [
    SCHEMAS / "video-paper-wiki.projection-input.v1.schema.json",
    SCHEMAS / "video-paper-wiki.projection-generation.v1.schema.json",
    SCHEMAS / "video-paper-wiki.catalog-rows.v1.schema.json",
]


def raw_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def walk_patterns(value: object):
    if isinstance(value, dict):
        if isinstance(value.get("pattern"), str):
            yield value["pattern"]
        for child in value.values():
            yield from walk_patterns(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_patterns(child)


def sample(pattern: str) -> str:
    choices = (
        ("source-ledger", "wiki/meta/ledgers/source-ledger.json"),
        ("claim-ledger", "wiki/meta/ledgers/claim-ledger.json"),
        ("taxonomy/v1", "taxonomy/v1.json"),
        ("records/papers", "wiki/meta/records/papers/paper.json"),
        ("records/repos", "wiki/meta/records/repos/repo.json"),
        ("meta/reviews", "wiki/meta/reviews/clm-" + "a" * 20 + "/ase-" + "b" * 20 + ".json"),
        ("raw/captured", ".raw/captured/" + "a" * 64 + ".py"),
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
    if "[0-9a-f]{64}" in pattern:
        return "a" * 64
    if "[\\x21-\\x7e]" in pattern:
        return "x"
    if "[a-z0-9]+(?:-[a-z0-9]+)*" in pattern:
        return "attrs"
    if "[0-9A-Za-z][0-9A-Za-z.+!-]*" in pattern:
        return "26.1.0"
    if "[a-z][a-z0-9_]*" in pattern:
        return "table_1"
    raise AssertionError(f"no safe sample for pattern {pattern!r}")


schemas = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(SCHEMAS.glob("*.schema.json"))]
assert len(schemas) == 21
assert len({item["title"] for item in schemas}) == 21
for schema in schemas:
    Draft202012Validator.check_schema(schema)

new_schemas = [json.loads(path.read_text(encoding="utf-8")) for path in NEW]
patterns = list(walk_patterns(new_schemas))
assert patterns and len(patterns) == 38
suffixes = ["\n", "\r", "\r\n", "\u2028", "\u2029"]
for pattern in patterns:
    valid = sample(pattern)
    validator = Draft202012Validator({"type": "string", "pattern": pattern})
    assert validator.is_valid(valid), (pattern, valid)
    for suffix in suffixes:
        assert not validator.is_valid(valid + suffix), (pattern, repr(suffix))

registry = Registry().with_resources((schema["$id"], Resource.from_contents(schema)) for schema in schemas)
by_title = {schema["title"]: schema for schema in schemas}
input_schema = by_title["video-paper-wiki.projection-input.v1"]
generation_schema = by_title["video-paper-wiki.projection-generation.v1"]
rows_schema = by_title["video-paper-wiki.catalog-rows.v1"]

hex64 = "a" * 64
entries = [
    {"path": "wiki/meta/ledgers/source-ledger.json", "kind": "source-ledger", "sha256": hex64, "size_bytes": 0},
    {"path": "wiki/meta/ledgers/claim-ledger.json", "kind": "claim-ledger", "sha256": hex64, "size_bytes": 0},
    {"path": "taxonomy/v1.json", "kind": "taxonomy", "sha256": hex64, "size_bytes": 0},
    {"path": "wiki/meta/records/papers/paper.json", "kind": "paper-record", "sha256": hex64, "size_bytes": 0},
    {"path": "wiki/meta/records/repos/repo.json", "kind": "repo-record", "sha256": hex64, "size_bytes": 0},
    {"path": "wiki/meta/reviews/clm-" + "a" * 20 + "/ase-" + "b" * 20 + ".json", "kind": "assessment-event", "sha256": hex64, "size_bytes": 0},
    {"path": ".raw/captured/" + hex64 + ".py", "kind": "captured-artifact", "sha256": hex64, "size_bytes": 0},
    {"path": ".raw/derived/" + hex64 + "/docling/" + hex64 + "/document.json", "kind": "docling-document", "sha256": hex64, "size_bytes": 0},
    {"path": ".raw/derived/" + hex64 + "/docling/" + hex64 + "/parser-config.json", "kind": "parser-config", "sha256": hex64, "size_bytes": 0},
    {"path": ".raw/derived/" + hex64 + "/docling/" + hex64 + "/model-manifest.json", "kind": "model-manifest", "sha256": hex64, "size_bytes": 0},
    {"path": ".raw/derived/" + hex64 + "/runs/run-1.json", "kind": "run-manifest", "sha256": hex64, "size_bytes": 0},
    {"path": ".raw/derived/code-manifests/" + hex64 + ".json", "kind": "code-evidence-manifest", "sha256": hex64, "size_bytes": 0},
    {"path": ".raw/derived/alignment-manifests/" + hex64 + ".json", "kind": "alignment-manifest", "sha256": hex64, "size_bytes": 0},
]
inventory = {"schema": "video-paper-wiki.projection-input.v1", "entries": entries}
Draft202012Validator(input_schema, registry=registry).validate(inventory)

file_item = {"path": "x", "sha256": hex64}
material = {
    "schema": "video-paper-wiki.projection-generation.v1",
    "profile": "base-catalog-v1",
    "inventory": inventory,
    "implementation": {"package_version": "0.1.0", "files": [file_item]},
    "resources": {"files": [file_item]},
    "dependencies": {
        "profile": "vpwiki-jsonschema-date-utc-v1",
        "distributions": [{"name": "attrs", "version": "26.1.0"}],
    },
    "upstream": {
        "commit": "9f8c1199047eac2c3828496279fbb7ba9540b90b",
        "version": "2.1.1",
        "files": [file_item],
    },
    "runtime": {
        "python_implementation": "CPython",
        "python_version": "3.13.13",
        "unicode_version": "15.1.0",
        "prefix_mode": "synthetic",
        "chunk_profile": "claude-obsidian.chunk.v1",
        "bm25_profile": "claude-obsidian.bm25.v2",
    },
}
Draft202012Validator(generation_schema, registry=registry).validate(material)
Draft202012Validator(rows_schema, registry=registry).validate({
    "schema": "video-paper-wiki.catalog-rows.v1",
    "ddl_sha256": hex64,
    "generation_sha256": hex64,
    "tables": [{"name": "x", "columns": ["x"], "rows": [[None]]}],
})

profile_path = CATALOG / "base-catalog-v1.generation-profile.json"
manifest_path = CATALOG / "base-catalog-v1.columns.json"
ddl_path = CATALOG / "base-catalog-v1.sql"
profile = json.loads(profile_path.read_text(encoding="utf-8"))
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

assert profile["material_keys"] == ["schema", "profile", "inventory", "implementation", "resources", "dependencies", "upstream", "runtime"]
assert len(profile["implementation"]["files"]) == 13
assert len(profile["resources"]["files"]) == 25
assert len(profile["upstream"]["files"]) == 8
assert profile["dependencies"]["profile"] == "vpwiki-jsonschema-date-utc-v1"
expected_counts = {"3.12.14": 6, "3.13.13": 5, "3.13.15": 5}
for item in profile["dependencies"]["accepted_exact_sets"]:
    distributions = item["distributions"]
    assert len(distributions) == expected_counts[item["python_version"]]
    assert [d["name"] for d in distributions] == sorted(d["name"] for d in distributions)
    assert all(set(d) == {"name", "version"} for d in distributions)

assert manifest["table_count"] == 34
assert manifest["column_count"] == 230
assert len(manifest["tables"]) == 34
assert sum(len(table["columns"]) for table in manifest["tables"]) == 230
assert len(manifest["semantic_checks"]) == 25
assert len({check["id"] for check in manifest["semantic_checks"]}) == 25
assert manifest["ddl_sha256"] == raw_sha(ddl_path)

connection = sqlite3.connect(":memory:")
connection.execute("PRAGMA foreign_keys=ON")
connection.executescript(ddl_path.read_text(encoding="utf-8"))
tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
assert len(tables) == 34
assert sum(len(connection.execute(f'PRAGMA table_info("{name}")').fetchall()) for name in tables) == 230
assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
connection.close()

seed = json.loads((ROOT / "docs/seed/engine-mvp.json").read_text(encoding="utf-8"))
assert len(seed["papers"]) == 67

result = {
    "checks": "pass",
    "schema_count": len(schemas),
    "strict_pattern_count": len(patterns),
    "strict_negative_vectors": len(patterns) * len(suffixes),
    "table_count": len(tables),
    "column_count": manifest["column_count"],
    "semantic_check_count": len(manifest["semantic_checks"]),
    "catalog_count": len(seed["papers"]),
    "sha256": {
        "ddl": raw_sha(ddl_path),
        "column_manifest": raw_sha(manifest_path),
        "generation_profile": raw_sha(profile_path),
        "projection_input_schema": raw_sha(NEW[0]),
        "projection_generation_schema": raw_sha(NEW[1]),
        "catalog_rows_schema": raw_sha(NEW[2]),
        "projection_input_contract": raw_sha(ROOT / "docs/ai/contracts/projection-input-v1.md"),
        "projection_catalog_contract": raw_sha(ROOT / "docs/ai/contracts/projection-catalog-v1.md"),
        "seed": raw_sha(ROOT / "docs/seed/engine-mvp.json"),
    },
}
Path("/tmp/vpkb-base-freeze-replay.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))
