"""Pure validation and canonical export of base-catalog relational rows."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from collections import defaultdict

from jsonschema import Draft202012Validator, validators

from video_paper_wiki.assessment_history import derive_assessment_heads
from video_paper_wiki.code_evidence_contracts import validate_code_evidence_manifest
from video_paper_wiki.contracts import ContractError, _registry, schema_by_title
from video_paper_wiki.identity import (
    IdentityError, claim_id, paper_page_slug, paper_subject_id, pipeline_fingerprint,
    repo_id as canonical_repo_id, repo_page_slug, repo_subject_id,
)
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.ledger_locator import decode_ledger_evidence, decode_ledger_locator, encode_ledger_locator
from video_paper_wiki.projection_generation import projection_generation_sha256
from video_paper_wiki.projection_input import validate_projection_inventory
from video_paper_wiki.projection_runtime import _preflight
from video_paper_wiki.resources import read_projection_resource_bytes

_DDL = "base-catalog-v1.sql"
_DDL_SHA = "3459beb249e348c869070220fda658cfd95c0f092fc12a18978baf19651a5c8c"
_MANIFEST = "base-catalog-v1.columns.json"
_MANIFEST_SHA = "439024fa2eed6695725c8fdfbe8d03e982e776160f5548f6201d99caaa0ee50c"
_PROFILE = "base-catalog-v1.generation-profile.json"
_PROFILE_SHA = "7b4e95e7b1ad89e492bab98486de359fe125854215fd2de5e7aaab3f4b8e333a"
_INT64_MIN, _INT64_MAX = -(1 << 63), (1 << 63) - 1
_OPAQUE = {"captured-artifact", "docling-document", "parser-config", "model-manifest"}
_ROOT_TABLE = {
    "source-ledger": "ledger_meta", "claim-ledger": "ledger_meta", "taxonomy": "taxonomy_meta",
    "paper-record": "papers", "repo-record": "repos", "assessment-event": "assessment_events",
    "run-manifest": "run_manifests", "code-evidence-manifest": "code_manifests",
    "alignment-manifest": "alignment_manifests",
}
_STRICT_TYPES = Draft202012Validator.TYPE_CHECKER.redefine("integer", lambda _c,v:type(v) is int).redefine("number",lambda _c,v:type(v) in (int,float))
_SchemaValidator = validators.extend(Draft202012Validator,type_checker=_STRICT_TYPES)
SEMANTIC_CHECK_IDS = (
    "exact-python-scalars", "inventory-profile", "inventory-declaration-only", "artifact-metadata-equality",
    "one-profile-per-input", "closed-schema-reconstruction", "ledger-roots", "contiguous-ordinals",
    "optional-array-presence", "owner-coverage", "supersedes-acyclic", "source-artifact-binding",
    "managed-page-addresses", "paper-active-extraction", "repo-paper-minimum", "complete-history",
    "taxonomy-profile", "tagged-locator-closure", "code-origin-manifest", "run-role-association",
    "alignment-five-capabilities", "alignment-required-children", "alignment-version-and-locator-binding",
    "row-export-order", "generation-binding",
)


def _fail(code: str, pointer: str, message: str) -> None:
    raise ContractError(code, message, {"instance_pointer": pointer})


def _closed_schema(document: dict, title: str, pointer: str) -> None:
    error=next(_SchemaValidator(schema_by_title(title),registry=_registry()[0]).iter_errors(document),None)
    if error is not None:_fail("CATALOG_ROWS_INVALID",pointer,"closed object reconstruction is invalid")


def _resource(name: str, digest: str) -> bytes:
    payload = read_projection_resource_bytes("catalog", name)
    if payload is None or hashlib.sha256(payload).hexdigest() != digest:
        _fail("CATALOG_RESOURCE_MISMATCH", "", "immutable catalog resource mismatch")
    return payload


def _resources() -> tuple[dict, dict]:
    _resource(_DDL, _DDL_SHA)
    try:
        manifest = json.loads(_resource(_MANIFEST, _MANIFEST_SHA))
        profile = json.loads(_resource(_PROFILE, _PROFILE_SHA))
    except (UnicodeError, json.JSONDecodeError):
        _fail("CATALOG_RESOURCE_MISMATCH", "", "immutable catalog resource is invalid")
    if (type(manifest) is not dict or type(profile) is not dict
            or manifest.get("ddl_sha256") != _DDL_SHA
            or manifest.get("table_count") != 34 or manifest.get("column_count") != 230
            or len(manifest.get("semantic_checks", [])) != 25):
        _fail("CATALOG_RESOURCE_MISMATCH", "", "catalog resources disagree")
    if tuple(x.get("id") for x in manifest["semantic_checks"]) != SEMANTIC_CHECK_IDS:
        _fail("CATALOG_RESOURCE_MISMATCH", "", "catalog semantic order differs")
    return manifest, profile


def _safe_preflight(generation_material: object, tables: object) -> None:
    try:
        _preflight({"generation_material": generation_material, "tables": tables})
    except ContractError as exc:
        if exc.code == "PROJECTION_LIMIT_EXCEEDED":
            raise
        pointer = exc.details.get("instance_pointer") if type(exc.details) is dict else None
        code = "PROJECTION_GENERATION_INVALID" if (
            pointer == "/generation_material" or (
                type(pointer) is str and pointer.startswith("/generation_material/")
            )
        ) else "CATALOG_ROWS_INVALID"
        raise ContractError(code, "unsupported catalog wrapper value", exc.details) from None


def _row_maps(
    manifest: dict, tables: object
) -> tuple[dict[str, list[dict]], dict[str, list[list]], dict[str, int]]:
    if type(tables) is not list:
        _fail("CATALOG_ROWS_INVALID", "/tables", "tables must be an exact list")
    definitions = {item["name"]: item for item in manifest["tables"]}
    supplied: dict[str, list[list]] = {}
    table_items: dict[str, dict] = {}
    positions: dict[str, int] = {}
    # Phase 4: collect the complete table set and validate only table/column/row
    # shape.  Scalar defects cannot mask a missing table or depend on caller table
    # order.
    for ti, item in enumerate(tables):
        base = f"/tables/{ti}"
        if type(item) is not dict or set(item) != {"name", "columns", "rows"}:
            _fail("CATALOG_ROWS_INVALID", base, "table object is not closed")
        name = item.get("name")
        if type(name) is not str or name not in definitions or name in supplied:
            _fail("CATALOG_ROWS_INVALID", base + "/name", "table name is missing, extra, or duplicated")
        definition = definitions[name]
        columns = [col["name"] for col in definition["columns"]]
        if type(item["columns"]) is not list or any(type(x) is not str for x in item["columns"]) or item["columns"] != columns:
            _fail("CATALOG_ROWS_INVALID", base + "/columns", "columns differ from manifest order")
        if type(item["rows"]) is not list:
            _fail("CATALOG_ROWS_INVALID", base + "/rows", "rows must be an exact list")
        for ri, row in enumerate(item["rows"]):
            pointer = f"{base}/rows/{ri}"
            if type(row) is not list or len(row) != len(columns):
                _fail("CATALOG_ROWS_INVALID", pointer, "row length differs from manifest")
        supplied[name] = item["rows"]
        table_items[name] = item
        positions[name] = ti
    if set(supplied) != set(definitions):
        _fail("CATALOG_ROWS_INVALID", "/tables", "complete table set is required")

    # Phase 5: exact cells, table CHECKs, then presence constraints, always in
    # frozen manifest order while retaining caller ordinals in diagnostics.
    maps: dict[str, list[dict]] = {}
    for definition in manifest["tables"]:
        name = definition["name"]
        converted = []
        for ri, row in enumerate(table_items[name]["rows"]):
            pointer = f"/tables/{positions[name]}/rows/{ri}"
            mapped = {}
            for ci, (value, column) in enumerate(zip(row, definition["columns"])):
                cp = f"{pointer}/{ci}"
                if value is None:
                    if not column["nullable"]:
                        _fail("CATALOG_ROWS_INVALID", cp, "nonnull column is null")
                elif column["type"] == "INTEGER":
                    if type(value) is not int or not _INT64_MIN <= value <= _INT64_MAX:
                        _fail("CATALOG_ROWS_INVALID", cp, "INTEGER cell is not exact int64")
                elif type(value) is not str:
                    _fail("CATALOG_ROWS_INVALID", cp, "TEXT cell is not exact string")
                else:
                    try:
                        value.encode("utf-8")
                    except UnicodeError:
                        _fail("CATALOG_ROWS_INVALID", cp, "TEXT cell contains a surrogate")
                if value is not None and "enum" in column and value not in column["enum"]:
                    _fail("CATALOG_ROWS_INVALID", cp, "cell is outside its enum")
                if type(value) is int and any(">= 0" in check for check in column.get("checks", [])) and value < 0:
                    _fail("CATALOG_ROWS_INVALID", cp, "integer cell is negative")
                if type(value) is int and any("<= 67108864" in check for check in column.get("checks", [])) and value > 67108864:
                    _fail("CATALOG_ROWS_INVALID", cp, "integer cell exceeds its bound")
                mapped[column["name"]] = value
            _table_check(name, mapped, pointer)
            for pair in definition["presence_pairs"]:
                if mapped[pair["presence_column"]] == 0 and mapped[pair["value_column"]] is not None:
                    _fail("CATALOG_ROWS_INVALID", pointer, "presence pair is inconsistent")
            converted.append(mapped)
        maps[name] = converted
    return maps, supplied, positions


def _relational(manifest: dict, rows: dict[str, list[dict]], positions: dict[str, int]) -> None:
    definitions = {x["name"]: x for x in manifest["tables"]}
    indexes: dict[tuple[str, tuple[str, ...]], set[tuple]] = {}
    table_names = [item["name"] for item in manifest["tables"]]
    # Phase 6a: primary keys.
    for name in table_names:
        definition = definitions[name]
        key = definition["primary_key"]
        values: set[tuple] = set()
        for ri, row in enumerate(rows[name]):
            item = tuple(row[x] for x in key)
            if item in values:
                _fail("CATALOG_ROWS_INVALID", f"/tables/{positions[name]}/rows/{ri}", "primary key is duplicated")
            values.add(item)
        indexes[(name, tuple(key))] = values
    # Phase 6b: unique keys.
    for name in table_names:
        definition = definitions[name]
        for key in definition["unique_keys"]:
            values: set[tuple] = set()
            for ri, row in enumerate(rows[name]):
                item = tuple(row[x] for x in key)
                if any(x is None for x in item):
                    continue
                if item in values:
                    _fail("CATALOG_ROWS_INVALID", f"/tables/{positions[name]}/rows/{ri}", "unique key is duplicated")
                values.add(item)
            indexes[(name, tuple(key))] = values
    # Phase 6c: foreign keys.
    for name in table_names:
        definition = definitions[name]
        for fk in definition["foreign_keys"]:
            target = indexes[(fk["target_table"], tuple(fk["target_columns"]))]
            for ri, row in enumerate(rows[name]):
                key = tuple(row[x] for x in fk["columns"])
                if any(x is None for x in key):
                    continue
                if key not in target:
                    _fail("CATALOG_ROWS_INVALID", f"/tables/{positions[name]}/rows/{ri}", "foreign key does not resolve")
    # Phase 6d: ordinal closure.
    for name in table_names:
        definition = definitions[name]
        for group in definition["ordinal_groups"]:
            grouped: dict[tuple, list[int]] = defaultdict(list)
            for row in rows[name]:
                grouped[tuple(row[x] for x in group["parent_columns"])].append(row[group["ordinal_column"]])
            for values in grouped.values():
                if sorted(values) != list(range(len(values))):
                    _fail("CATALOG_ROWS_INVALID", f"/tables/{positions[name]}", "ordinals are not contiguous")


def _table_check(name: str, row: dict, pointer: str) -> None:
    if name == "ledger_meta":
        valid = ((row["ledger_kind"] == "source" and row["schema"] == "claude-obsidian.source-ledger.v1" and row["input_path"] == "wiki/meta/ledgers/source-ledger.json")
                 or (row["ledger_kind"] == "claim" and row["schema"] == "claude-obsidian.claim-ledger.v1" and row["input_path"] == "wiki/meta/ledgers/claim-ledger.json"))
        if not valid:
            _fail("CATALOG_ROWS_INVALID", pointer, "ledger root tuple is invalid")
    elif name == "taxonomy_meta" and row["input_path"] != "taxonomy/v1.json":
        _fail("CATALOG_ROWS_INVALID", pointer, "taxonomy path is invalid")
    elif name == "subjects":
        if not ((row["owner_kind"] == "paper" and row["paper_id"] is not None and row["repo_id"] is None)
                or (row["owner_kind"] == "repo" and row["repo_id"] is not None and row["paper_id"] is None)):
            _fail("CATALOG_ROWS_INVALID", pointer, "subject owner XOR is invalid")
    elif name == "claim_refs":
        if not ((row["section"] is not None and row["core"] is not None and row["capability"] is None)
                or (row["section"] is None and row["core"] is None and row["capability"] is not None)):
            _fail("CATALOG_ROWS_INVALID", pointer, "claim reference shape is invalid")
    elif name == "assessment_events":
        genesis = row["actor_kind"] == "system" and row["transition_kind"] == "genesis" and row["previous_event_id"] is None and row["from_assessment"] is None and row["to_assessment"] == "provisional"
        invalidation = row["actor_kind"] == "system" and row["transition_kind"] == "evidence_invalidation" and row["previous_event_id"] is not None and row["from_assessment"] is not None and row["to_assessment"] == "provisional"
        human = row["actor_kind"] == "human" and row["transition_kind"] == "human_assessment" and row["previous_event_id"] is not None and row["from_assessment"] is not None and row["to_assessment"] != "provisional" and row["from_assessment"] != row["to_assessment"]
        if not (genesis or invalidation or human):
            _fail("CATALOG_ROWS_INVALID", pointer, "assessment transition is invalid")
    elif name == "alignment_capabilities":
        present = row["absence_scope_present"]
        if not ((present == 0 and row["absence_commit"] is None and row["absence_tree_prefix"] is None)
                or (present == 1 and row["absence_commit"] is not None and row["absence_tree_prefix"] is not None)):
            _fail("CATALOG_ROWS_INVALID", pointer, "absence scope is inconsistent")
        if row["status"] == "absent" and present != 1:
            _fail("CATALOG_ROWS_INVALID", pointer, "absent capability lacks scope")
        if row["checkpoint_kind"] is not None and row["name"] != "checkpoints":
            _fail("CATALOG_ROWS_INVALID", pointer, "checkpoint kind is misplaced")
    elif name == "sources":
        if (row["content_kind"] == "synthetic") != (row["authority"] == "synthetic"):
            _fail("CATALOG_ROWS_INVALID", pointer, "synthetic source invariant fails")


def _graph(rows: list[dict], key: str, edge: str) -> None:
    by = {r[key]: r for r in rows}
    for start in by:
        seen = set()
        current = start
        while current is not None:
            if current in seen:
                _fail("CATALOG_ROWS_INVALID", "/tables", "supersedes graph has a cycle")
            seen.add(current)
            current = by[current][edge]


def _semantic(manifest: dict, generation: dict, rows: dict[str, list[dict]]) -> None:
    # Checks 1-3 were enforced by shape/cells and generation/input validation.
    inv = generation["inventory"]
    validate_projection_inventory(inv)
    declared = {(x["path"], x["kind"], x["sha256"], x["size_bytes"]) for x in inv["entries"]}
    projected = {(x["path"], x["kind"], x["file_sha256"], x["size_bytes"]) for x in rows["canonical_inputs"]}
    if declared != projected:
        _fail("CATALOG_ROWS_INVALID", "/tables/canonical_inputs", "inventory rows differ from generation inventory")
    inputs = {x["path"]: x for x in rows["canonical_inputs"]}
    artifacts = {x["artifact_path"]: x for x in rows["artifacts"]}
    for path, artifact in artifacts.items():
        source = inputs[path]
        if artifact["artifact_kind"] != source["kind"] or artifact["size_bytes"] != source["size_bytes"]:
            _fail("CATALOG_ROWS_INVALID", "/tables/artifacts", "artifact metadata differs")
    for item in inputs.values():
        table = "artifacts" if item["kind"] in _OPAQUE else _ROOT_TABLE[item["kind"]]
        column = "artifact_path" if table == "artifacts" else "input_path"
        count = sum(r[column] == item["path"] for r in rows[table])
        if count != 1:
            _fail("CATALOG_ROWS_INVALID", f"/tables/{table}", "input has no unique typed root")
    _closed_reconstruction(rows)
    ledgers = {r["ledger_kind"]: r for r in rows["ledger_meta"]}
    if set(ledgers) != {"source", "claim"}:
        _fail("CATALOG_ROWS_INVALID", "/tables/ledger_meta", "both ledger roots are required")
    _optional_arrays(rows)
    _owner_coverage(rows)
    for name in ("sources", "claims"):
        _graph(rows[name], "source_id" if name == "sources" else "claim_id", "supersedes")
    source_artifacts = {x["source_id"]: x for x in rows["source_artifacts"]}
    for source in rows["sources"]:
        bound = source_artifacts.get(source["source_id"])
        if source["origin_kind"] == "file":
            if source["content_sha256_present"] != 1 or source["content_sha256"] is None or bound is None:
                _fail("CATALOG_ROWS_INVALID", "/tables/sources", "file source is not captured")
            artifact = artifacts[bound["artifact_path"]]
            if bound["artifact_path"] != source["origin_locator"] or artifact["artifact_kind"] != "captured-artifact" or artifact["file_sha256"] != source["content_sha256"]:
                _fail("CATALOG_ROWS_INVALID", "/tables/source_artifacts", "file source capture differs")
        elif bound is not None:
            _fail("CATALOG_ROWS_INVALID", "/tables/source_artifacts", "non-file source has an artifact")
    _managed_pages(rows)
    _active_extractions(rows, artifacts)
    if any(not any(x["repo_id"] == repo["repo_id"] for x in rows["repo_papers"]) for repo in rows["repos"]):
        _fail("CATALOG_ROWS_INVALID", "/tables/repo_papers", "repo has no paper")
    _history(rows)
    _taxonomy(rows)
    _locators(rows)
    _code(rows)
    _runs(rows, artifacts)
    _alignments(rows)


def _closed_reconstruction(rows: dict[str, list[dict]]) -> None:
    sha = re.compile(r"[0-9a-f]{64}")
    identifiers = {
        "sources": ("source_id", re.compile(r"src-[0-9a-f]{20}")),
        "claims": ("claim_id", re.compile(r"clm-[0-9a-f]{20}")),
        "assessment_events": ("event_id", re.compile(r"ase-[0-9a-f]{20}")),
    }
    for table, (field, pattern) in identifiers.items():
        if any(not pattern.fullmatch(row[field]) for row in rows[table]):
            _fail("CATALOG_ROWS_INVALID", f"/tables/{table}", "identifier grammar differs")
    for table in rows:
        for row in rows[table]:
            for field, value in row.items():
                if value is not None and (field.endswith("sha256") or field.endswith("_fingerprint")):
                    if not sha.fullmatch(value):
                        _fail("CATALOG_ROWS_INVALID", f"/tables/{table}", "digest grammar differs")
    for row in rows["ledger_meta"]:
        _utc(row["generated_at"], fractional=False)
    for row in rows["sources"]:
        if not row["title"].strip() or not row["origin_locator"] or (row["independence_key"] is not None and not row["independence_key"].strip()):
            _fail("CATALOG_ROWS_INVALID", "/tables/sources", "source text is blank")
        for field in ("ingested_at", "retrieved_at", "refresh_due"):
            if row[field] is not None: _date(row[field])
        if row["ingested_at"] is not None and row["content_sha256"] is None:
            _fail("CATALOG_ROWS_INVALID", "/tables/sources", "ingested source lacks content hash")
        observed = row["retrieved_at"] or row["ingested_at"]
        if row["review_status"] == "active" and (observed is None or row["refresh_due"] is None):
            _fail("CATALOG_ROWS_INVALID", "/tables/sources", "active source dates are incomplete")
        if observed is not None and row["refresh_due"] is not None and row["refresh_due"] < observed:
            _fail("CATALOG_ROWS_INVALID", "/tables/sources", "source refresh precedes observation")
    for row in rows["claims"]:
        if not row["text"].strip() or len(row["text"].encode("utf-8")) > 65536:
            _fail("CATALOG_ROWS_INVALID", "/tables/claims", "claim text is invalid")
        if row["reviewed_at"] is not None: _date(row["reviewed_at"])
        if row["assessment"] == "accepted" and row["reviewed_at"] is None:
            _fail("CATALOG_ROWS_INVALID", "/tables/claims", "accepted claim lacks review date")
        if row["assessment"] == "contested":
            opposed = any(x["claim_id"] == row["claim_id"] and x["wire_relation"] == "contradicts" for x in rows["claim_evidence"])
            if not opposed and not (row["notes"] is not None and row["notes"].strip()):
                _fail("CATALOG_ROWS_INVALID", "/tables/claims", "contested claim lacks rationale")
    for row in rows["papers"]:
        _date(row["published_at"]); _utc(row["created_at"]); _utc(row["updated_at"])
    for row in rows["repos"]:
        _utc(row["created_at"]); _utc(row["updated_at"])
    for row in rows["assessment_events"]:
        _utc(row["decided_at"])
        expected=f"wiki/meta/reviews/{row['claim_id']}/{row['event_id']}.json"
        if row["input_path"]!=expected:_fail("CATALOG_ROWS_INVALID", "/tables/assessment_events", "assessment path identity differs")
    for row in rows["run_manifests"]:
        _utc(row["started_at"]); _utc(row["ended_at"])
    _reconstruct_records(rows)


def _date(value: str) -> None:
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",value) is None:
        _fail("CATALOG_ROWS_INVALID", "/tables", "date spelling is invalid")
    try: date.fromisoformat(value)
    except (ValueError, TypeError): _fail("CATALOG_ROWS_INVALID", "/tables", "date is invalid")


def _utc(value: str, *, fractional: bool = True) -> None:
    pattern = r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?Z" if fractional else r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z"
    if not re.fullmatch(pattern, value): _fail("CATALOG_ROWS_INVALID", "/tables", "UTC spelling is invalid")
    try: datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError: _fail("CATALOG_ROWS_INVALID", "/tables", "UTC clock is invalid")


def _children(rows, table, parent, value):
    return sorted((x for x in rows[table] if x[parent] == value), key=lambda x: x["ordinal"])


def _reconstruct_records(rows: dict[str, list[dict]]) -> None:
    for row in rows["papers"]:
        pid=row["paper_id"]
        doc={"schema":row["schema"],"paper_id":pid,"title":row["title"],"title_zh":row["title_zh"],
             "authors":[x["author"] for x in _children(rows,"paper_authors","paper_id",pid)],
             "published_at":row["published_at"],"aliases":[x["alias"] for x in _children(rows,"paper_aliases","paper_id",pid)],
             "source_ids":[x["source_id"] for x in _children(rows,"paper_sources","paper_id",pid)],
             "taxonomy":[{"axis":x["axis"],"slug":x["slug"]} for x in _children(rows,"paper_taxonomy","paper_id",pid)],
             "section_claim_refs":[{"section":x["section"],"claim_id":x["claim_id"],"core":bool(x["core"]),"lifecycle":x["lifecycle"]}
                                   for x in sorted((x for x in rows["claim_refs"] if x["subject_id"]==f"paper:{pid}"),key=lambda x:x["ordinal"])],
             "created_at":row["created_at"],"updated_at":row["updated_at"]}
        for key in ("arxiv_id","doi","active_extraction_path","active_extraction_sha256"):
            if row[key] is not None: doc[key]=row[key]
        if row["code_urls_present"]: doc["code_urls"]=[x["url"] for x in _children(rows,"paper_code_urls","paper_id",pid)]
        _closed_schema(doc,"video-paper-wiki.paper-record.v1","/tables/papers")
        try: paper_page_slug(pid)
        except IdentityError:_fail("CATALOG_ROWS_INVALID", "/tables/papers", "paper identity is invalid")
    for row in rows["repos"]:
        rid=row["repo_id"]
        doc={"schema":row["schema"],"repo_id":rid,"canonical_repository":row["canonical_repository"],"canonical_commit":row["canonical_commit"],
             "paper_ids":[x["paper_id"] for x in _children(rows,"repo_papers","repo_id",rid)],"officiality":row["officiality"],
             "license":{"spdx_id":row["license_spdx_id"],"notes":row["license_notes"]},
             "capability_claim_refs":[{"capability":x["capability"],"claim_id":x["claim_id"],"lifecycle":x["lifecycle"]}
                                      for x in sorted((x for x in rows["claim_refs"] if x["subject_id"]==f"repo:{rid}"),key=lambda x:x["ordinal"])],
             "created_at":row["created_at"],"updated_at":row["updated_at"]}
        if row["archived"] is not None: doc["archived"]=bool(row["archived"])
        _closed_schema(doc,"video-paper-wiki.repo-record.v1","/tables/repos")
        if canonical_repo_id(row["canonical_repository"])!=rid:_fail("CATALOG_ROWS_INVALID", "/tables/repos", "repo identity is invalid")


def _active_extractions(rows: dict[str, list[dict]], artifacts: dict[str, dict]) -> None:
    paper_sources=defaultdict(set)
    for x in rows["paper_sources"]: paper_sources[x["paper_id"]].add(x["source_id"])
    source_by={x["source_id"]:x for x in rows["sources"]}; bindings={x["source_id"]:x["artifact_path"] for x in rows["source_artifacts"]}
    run_roles=defaultdict(dict)
    for x in rows["run_artifact_bindings"]:run_roles[x["run_path"]][x["role"]]=x["artifact_path"]
    runs={x["input_path"]:x for x in rows["run_manifests"]}
    for paper in rows["papers"]:
        path=paper["active_extraction_path"]
        if (path is None)!=(paper["active_extraction_sha256"] is None): _fail("CATALOG_ROWS_INVALID", "/tables/papers", "active extraction pair differs")
        if path is None: continue
        if path not in artifacts or artifacts[path]["artifact_kind"]!="docling-document" or artifacts[path]["file_sha256"]!=paper["active_extraction_sha256"]:
            _fail("CATALOG_ROWS_INVALID", "/tables/papers", "active extraction artifact differs")
        contexts=[]
        for run_path,roles in run_roles.items():
            if roles.get("document")==path and runs[run_path]["error_code"] is None: contexts.append(roles.get("source"))
        ok=False
        for captured in contexts:
            for sid in paper_sources[paper["paper_id"]]:
                source=source_by[sid]
                if source["origin_kind"]=="file" and source["content_kind"]=="document" and bindings.get(sid)==captured:ok=True
        if not ok:_fail("CATALOG_ROWS_INVALID", "/tables/papers", "active extraction has no qualifying source run")


def _optional_arrays(rows: dict[str, list[dict]]) -> None:
    present = {x["paper_id"]: x["code_urls_present"] for x in rows["papers"]}
    children = {x["paper_id"] for x in rows["paper_code_urls"]}
    if any(bit == 0 and pid in children for pid, bit in present.items()):
        _fail("CATALOG_ROWS_INVALID", "/tables/paper_code_urls", "absent code URL array has children")


def _owner_coverage(rows: dict[str, list[dict]]) -> None:
    subjects = {x["subject_id"]: x for x in rows["subjects"]}
    papers = {x["paper_id"]: x for x in rows["papers"]}
    repos = {x["repo_id"]: x for x in rows["repos"]}
    if len(subjects) != len(papers) + len(repos):
        _fail("CATALOG_ROWS_INVALID", "/tables/subjects", "one subject per owner is required")
    for subject in subjects.values():
        expected = paper_subject_id(subject["paper_id"]) if subject["owner_kind"] == "paper" else repo_subject_id(subject["repo_id"])
        if expected != subject["subject_id"]:
            _fail("CATALOG_ROWS_INVALID", "/tables/subjects", "subject identity differs")
    refs = {x["claim_id"]: x for x in rows["claim_refs"]}
    claims = {x["claim_id"]: x for x in rows["claims"]}
    if set(refs) != set(claims):
        _fail("CATALOG_ROWS_INVALID", "/tables/claim_refs", "every claim needs one owner")
    for cid, ref in refs.items():
        subject = subjects[ref["subject_id"]]
        if claim_id(subject["subject_id"], claims[cid]["text"]) != cid:
            _fail("CATALOG_ROWS_INVALID", "/tables/claims", "claim identity differs")
        location = (f"wiki/papers/{paper_page_slug(subject['paper_id'])}.md" if subject["owner_kind"] == "paper"
                    else f"wiki/code/{repo_page_slug(subject['repo_id'])}.md")
        if claims[cid]["location_path"] != location:
            _fail("CATALOG_ROWS_INVALID", "/tables/claims", "claim owner page differs")


def _managed_pages(rows: dict[str, list[dict]]) -> None:
    pages = {f"wiki/papers/{paper_page_slug(x['paper_id'])}.md" for x in rows["papers"]}
    pages |= {f"wiki/code/{repo_page_slug(x['repo_id'])}.md" for x in rows["repos"]}
    pages |= {f"wiki/concepts/{x['axis']}/{x['slug']}.md" for x in rows["taxonomy_terms"]}
    if any(x["page_path"] not in pages for x in rows["source_pages"]):
        _fail("CATALOG_ROWS_INVALID", "/tables/source_pages", "source page is unmanaged")


def _history(rows: dict[str, list[dict]]) -> None:
    evidence = defaultdict(list)
    relation = {"supports": "supports", "contradicts": "contradicts", "context": "uncertain"}
    for item in rows["claim_evidence"]:
        decoded = decode_ledger_evidence({"source_id": item["source_id"], "relation": item["wire_relation"], "locator": item["locator_wire"]})
        evidence[item["claim_id"]].append(decoded)
    refs = {r["claim_id"]: r for r in rows["claim_refs"]}
    claims = []
    for row in rows["claims"]:
        claims.append({"claim_id": row["claim_id"], "stable_subject_id": refs[row["claim_id"]]["subject_id"],
                       "canonical_claim_text": row["text"], "evidence": evidence[row["claim_id"]],
                       "assessment": row["assessment"], "reviewed_at": row["reviewed_at"]})
    events = [{k: r[k] for k in ("schema", "claim_id", "previous_event_id", "actor_kind", "transition_kind",
                                  "from_assessment", "to_assessment", "claim_text_sha256", "evidence_fingerprint",
                                  "decided_by", "decided_at", "reason")} | {"event_id": r["event_id"]}
              for r in rows["assessment_events"]]
    try:
        heads = derive_assessment_heads(claims=claims, events=events)
    except ContractError:
        _fail("CATALOG_ROWS_INVALID", "/tables/assessment_events", "assessment history is invalid")
    if heads != {r["claim_id"]: r["head_event_id"] for r in rows["assessment_heads"]}:
        _fail("CATALOG_ROWS_INVALID", "/tables/assessment_heads", "assessment heads differ")


def _taxonomy(rows: dict[str, list[dict]]) -> None:
    expected_axes = ["task/conditioning", "formulation/objective", "representation/tokenizer", "backbone",
                     "spatial-temporal-modeling", "data/captioning/filtering", "training/parallelism/optimization",
                     "inference/distillation/acceleration", "control", "evaluation/dataset/benchmark"]
    meta = rows["taxonomy_meta"]
    if len(meta) != 1 or tuple(meta[0][x] for x in ("input_path", "version", "unknown_terms", "silent_create", "statement_en", "statement_zh")) != (
        "taxonomy/v1.json", "v1", "review_queue", 0,
        "Unknown terms MUST enter a review queue and MUST NOT be silently created as canonical terms.",
        "未知术语必须进入 review queue，不得静默创建新的 canonical term。"):
        _fail("CATALOG_ROWS_INVALID", "/tables/taxonomy_meta", "taxonomy policy differs")
    axes = sorted(rows["taxonomy_axes"], key=lambda x: x["ordinal"])
    if [x["axis"] for x in axes] != expected_axes:
        _fail("CATALOG_ROWS_INVALID", "/tables/taxonomy_axes", "taxonomy axes differ")
    for axis in expected_axes:
        terms = [x for x in rows["taxonomy_terms"] if x["axis"] == axis]
        if not terms or any(x["status"] != "canonical" or not x["label_zh"].encode("utf-8")
                            or re.fullmatch(r"[a-z0-9]+(?:[-_][a-z0-9]+)*",x["slug"]) is None for x in terms):
            _fail("CATALOG_ROWS_INVALID", "/tables/taxonomy_terms", "taxonomy terms differ")
    for table, field in (("taxonomy_axes", "label_zh"), ("taxonomy_axes", "label_en"),
                         ("taxonomy_axis_aliases", "alias"), ("taxonomy_term_aliases", "alias")):
        if any(len(x[field].encode("utf-8")) == 0 for x in rows[table]):
            _fail("CATALOG_ROWS_INVALID", f"/tables/{table}", "taxonomy text is empty")


def _locators(rows: dict[str, list[dict]]) -> None:
    subjects={x["subject_id"]:x for x in rows["subjects"]}; refs={x["claim_id"]:x for x in rows["claim_refs"]}
    paper_sources=defaultdict(set)
    for x in rows["paper_sources"]:paper_sources[x["paper_id"]].add(x["source_id"])
    repo_papers=defaultdict(set)
    for x in rows["repo_papers"]:repo_papers[x["repo_id"]].add(x["paper_id"])
    manifests=rows["code_manifests"]
    inputs={x["path"]:x for x in rows["canonical_inputs"]}
    source_artifacts={x["source_id"]:x["artifact_path"] for x in rows["source_artifacts"]}
    run_by={x["input_path"]:x for x in rows["run_manifests"]}; qualifying=set()
    for binding in rows["run_artifact_bindings"]:
        if binding["role"]=="document" and run_by[binding["run_path"]]["error_code"] is None:qualifying.add(binding["artifact_path"])
    def pdf_ok(decoded):
        match=re.fullmatch(r"\.raw/derived/([0-9a-f]{64})/docling/[0-9a-f]{64}/document\.json",decoded["artifact_path"])
        captured=source_artifacts.get(decoded["source_id"])
        return (match is not None and captured in inputs and inputs[captured]["file_sha256"]==match.group(1)
                and decoded["artifact_path"] in qualifying and decoded["artifact_path"] in inputs
                and inputs[decoded["artifact_path"]]["kind"]=="docling-document"
                and inputs[decoded["artifact_path"]]["file_sha256"]==decoded["artifact_sha256"])
    def member(source_id, subject):
        if subject["owner_kind"]=="paper":return source_id in paper_sources[subject["paper_id"]]
        return any(source_id in paper_sources[p] for p in repo_papers[subject["repo_id"]])
    for item in rows["claim_evidence"]:
        try:
            decoded = decode_ledger_evidence({"source_id": item["source_id"], "relation": item["wire_relation"], "locator": item["locator_wire"]})
        except ContractError:
            _fail("CATALOG_ROWS_INVALID", "/tables/claim_evidence", "claim locator is invalid")
        subject=subjects[refs[item["claim_id"]]["subject_id"]]
        if decoded["kind"]=="pdf" and (not member(item["source_id"],subject) or not pdf_ok(decoded)):
            _fail("CATALOG_ROWS_INVALID", "/tables/claim_evidence", "PDF locator owner/document differs")
        if decoded["kind"]=="code":
            rid=canonical_repo_id(decoded["repository"])
            if subject["owner_kind"]=="repo" and rid!=subject["repo_id"]:_fail("CATALOG_ROWS_INVALID", "/tables/claim_evidence", "code locator repo differs")
            if subject["owner_kind"]=="paper" and not any(x["repo_id"]==rid and x["paper_id"]==subject["paper_id"] for x in rows["repo_papers"]):_fail("CATALOG_ROWS_INVALID", "/tables/claim_evidence", "code locator repo is not linked")
            if not any(x["repo_id"]==rid and x["commit"]==decoded["commit"] and x["origin_path"]==decoded["path"] and x["source_id"]==decoded["source_id"] for x in manifests):_fail("CATALOG_ROWS_INVALID", "/tables/claim_evidence", "code locator manifest differs")
    for table, kind in (("alignment_officiality_evidence", "pdf"), ("alignment_capability_locators", "code")):
        for item in rows[table]:
            try:
                decoded = decode_ledger_locator(item["locator_wire"])
                if decoded["source_id"] != item["source_id"] or decoded["kind"] != kind or encode_ledger_locator(decoded) != item["locator_wire"]:
                    raise ValueError
            except (ContractError, ValueError, KeyError):
                _fail("CATALOG_ROWS_INVALID", f"/tables/{table}", "alignment locator is invalid")
            alignment=next(x for x in rows["alignment_manifests"] if x["input_path"]==item["alignment_path"])
            if kind=="pdf" and item["source_id"] not in paper_sources[alignment["paper_id"]]:
                _fail("CATALOG_ROWS_INVALID", f"/tables/{table}", "alignment PDF source is outside paper")
            if kind=="pdf" and not pdf_ok(decoded):
                _fail("CATALOG_ROWS_INVALID", f"/tables/{table}", "alignment PDF document differs")
            if kind=="code":
                if canonical_repo_id(decoded["repository"])!=alignment["repo_id"] or decoded["commit"]!=alignment["commit"]:
                    _fail("CATALOG_ROWS_INVALID", f"/tables/{table}", "alignment code version differs")
                if not any(x["repo_id"]==alignment["repo_id"] and x["commit"]==alignment["commit"] and x["origin_path"]==decoded["path"] and x["source_id"]==decoded["source_id"] for x in rows["code_manifests"]):
                    _fail("CATALOG_ROWS_INVALID", f"/tables/{table}", "alignment code manifest differs")


def _code(rows: dict[str, list[dict]]) -> None:
    origins = {(x["repo_id"], x["commit"], x["origin_path"], x["source_id"]) for x in rows["code_origins"]}
    sources={x["source_id"]:x for x in rows["sources"]}; bindings={x["source_id"]:x["artifact_path"] for x in rows["source_artifacts"]}
    inputs={x["path"]:x for x in rows["canonical_inputs"]}
    artifacts={x["artifact_path"]:x for x in rows["artifacts"]}
    used = set()
    for row in rows["code_manifests"]:
        if canonical_repo_id(row["repository"]) != row["repo_id"]:
            _fail("CATALOG_ROWS_INVALID", "/tables/code_manifests", "code repo identity differs")
        key = (row["repo_id"], row["commit"], row["origin_path"], row["source_id"]); used.add(key)
        source=sources[row["source_id"]]
        if artifacts[row["stored_path"]]["size_bytes"]!=row["payload_size_bytes"]:
            _fail("CATALOG_ROWS_INVALID", "/tables/code_manifests", "code payload size differs from capture")
        if source["origin_kind"]!="file" or source["content_kind"]!="code" or bindings.get(row["source_id"])!=row["stored_path"] or source["content_sha256"]!=row["payload_sha256"]:
            _fail("CATALOG_ROWS_INVALID", "/tables/code_manifests", "code capture source differs")
        document = {"schema": row["schema"], "state": row["state"],
                    "origin": {"repository": row["repository"], "commit": row["commit"], "path": row["origin_path"]},
                    "payload": {"sha256": row["payload_sha256"], "size_bytes": row["payload_size_bytes"]},
                    "media_type": row["media_type"], "encoding": row["encoding"],
                    "line_canonicalization": row["line_canonicalization"], "newline_style": row["newline_style"],
                    "ends_with_newline": bool(row["ends_with_newline"]), "line_count": row["line_count"],
                    "normalized_sha256": row["normalized_sha256"], "proposal_sha256": row["proposal_sha256"],
                    "capture": {"stored_path": row["stored_path"], "source_identity": row["source_identity"],
                                "source_id": row["source_id"], "inspection_approval_hash": row["inspection_approval_hash"],
                                "operation_id": row["operation_id"]}, "manifest_sha256": row["manifest_sha256"]}
        try: validate_code_evidence_manifest(document)
        except ContractError: _fail("CATALOG_ROWS_INVALID", "/tables/code_manifests", "code manifest is invalid")
    if origins != used:
        _fail("CATALOG_ROWS_INVALID", "/tables/code_origins", "orphan code origin exists")


def _runs(rows: dict[str, list[dict]], artifacts: dict[str, dict]) -> None:
    bindings = defaultdict(dict)
    for x in rows["run_artifact_bindings"]: bindings[x["run_path"]][x["role"]] = x["artifact_path"]
    used_config_model = set()
    source_artifact_ids=defaultdict(set)
    source_rows={x["source_id"]:x for x in rows["sources"]}
    for x in rows["source_artifacts"]:source_artifact_ids[x["artifact_path"]].add(x["source_id"])
    for run in rows["run_manifests"]:
        roles = bindings[run["input_path"]]
        path_match = re.fullmatch(r"\.raw/derived/([0-9a-f]{64})/runs/([^/]+)\.json", run["input_path"])
        if path_match is None or path_match.group(2) != run["run_id"]:
            _fail("CATALOG_ROWS_INVALID", "/tables/run_manifests", "run path identity differs")
        source_sha = path_match.group(1)
        document={"schema":run["schema"],"run_id":run["run_id"],
                  "tool_versions":{"vpwiki":run["vpwiki_version"],"python":run["python_version"]},
                  "input_hashes":{},"output_hashes":{},"started_at":run["started_at"],"ended_at":run["ended_at"],"error_code":run["error_code"]}
        for field,key in (("docling_version","docling"),("docling_core_version","docling_core"),("claude_obsidian_version","claude_obsidian")):
            if run[field] is not None:document["tool_versions"][key]=run[field]
        for field,key in (("input_ingest_plan_sha256","ingest_plan_sha256"),("input_prepared_sha256","prepared_sha256"),("input_source_sha256","source_sha256"),("input_parser_config_sha256","parser_config_sha256"),("input_model_manifest_sha256","model_manifest_sha256")):
            if run[field] is not None:document["input_hashes"][key]=run[field]
        for field,key in (("output_document_json_sha256","document_json_sha256"),("output_draft_sha256","draft_sha256"),("output_receipt_sha256","receipt_sha256")):
            if run[field] is not None:document["output_hashes"][key]=run[field]
        if run["pipeline_fingerprint"] is not None:document["pipeline_fingerprint"]=run["pipeline_fingerprint"]
        _closed_schema(document,"video-paper-wiki.run-manifest.v1","/tables/run_manifests")
        if set(roles) - {"source", "parser_config", "model_manifest", "document"} or "source" not in roles:
            _fail("CATALOG_ROWS_INVALID", "/tables/run_artifact_bindings", "run roles differ")
        if roles["source"] not in artifacts or artifacts[roles["source"]]["artifact_kind"] != "captured-artifact" or artifacts[roles["source"]]["file_sha256"] != source_sha:
            _fail("CATALOG_ROWS_INVALID", "/tables/run_artifact_bindings", "run source context differs")
        if not any(source_rows[sid]["origin_kind"]=="file" for sid in source_artifact_ids[roles["source"]]):
            _fail("CATALOG_ROWS_INVALID", "/tables/run_artifact_bindings", "run source has no logical file source")
        if run["input_source_sha256"] is not None and run["input_source_sha256"] != source_sha:
            _fail("CATALOG_ROWS_INVALID", "/tables/run_manifests", "declared run source differs")
        fp = run["pipeline_fingerprint"]
        named = (run["input_parser_config_sha256"], run["input_model_manifest_sha256"], run["output_document_json_sha256"])
        if fp is None:
            if any(x is not None for x in named) or set(roles) != {"source"}:
                _fail("CATALOG_ROWS_INVALID", "/tables/run_manifests", "unbound run has derived roles")
        else:
            if None in named or run["docling_version"] != "2.117.0" or run["docling_core_version"] != "2.92.0":
                _fail("CATALOG_ROWS_INVALID", "/tables/run_manifests", "pipeline tuple is incomplete")
            bound = {"engine": "docling", "engine_version": run["docling_version"], "core_version": run["docling_core_version"],
                     "config_sha256": named[0], "model_manifest_sha256": named[1]}
            if pipeline_fingerprint(bound) != fp or set(roles) != {"source", "parser_config", "model_manifest", "document"}:
                _fail("CATALOG_ROWS_INVALID", "/tables/run_manifests", "pipeline binding differs")
            for role, digest in zip(("parser_config", "model_manifest", "document"), named):
                suffix={"parser_config":"parser-config.json","model_manifest":"model-manifest.json","document":"document.json"}[role]
                expected=f".raw/derived/{source_sha}/docling/{fp}/{suffix}"
                if roles[role] != expected or artifacts[roles[role]]["file_sha256"] != digest:
                    _fail("CATALOG_ROWS_INVALID", "/tables/run_artifact_bindings", "run artifact digest differs")
                if role != "document": used_config_model.add(roles[role])
    expected = {p for p,a in artifacts.items() if a["artifact_kind"] in {"parser-config", "model-manifest"}}
    if expected != used_config_model:
        _fail("CATALOG_ROWS_INVALID", "/tables/run_artifact_bindings", "config/model artifact is unreferenced")
    for path, artifact in artifacts.items():
        if artifact["artifact_kind"] != "docling-document": continue
        qualifying=[]
        for run in rows["run_manifests"]:
            roles=bindings[run["input_path"]]
            if roles.get("document")==path and run["error_code"] is None and roles.get("parser_config") in artifacts and roles.get("model_manifest") in artifacts:
                qualifying.append(run)
        if not qualifying:
            _fail("CATALOG_ROWS_INVALID", "/tables/run_manifests", "document has no qualifying run")


def _alignments(rows: dict[str, list[dict]]) -> None:
    caps = defaultdict(list); locs = defaultdict(list); patterns = defaultdict(list); official = defaultdict(list)
    for x in rows["alignment_capabilities"]: caps[x["alignment_path"]].append(x)
    for x in rows["alignment_capability_locators"]: locs[(x["alignment_path"],x["capability_name"])].append(x)
    for x in rows["alignment_absence_patterns"]: patterns[(x["alignment_path"],x["capability_name"])].append(x)
    for x in rows["alignment_officiality_evidence"]: official[x["alignment_path"]].append(x)
    names={"training","inference","data","evaluation","checkpoints"}
    for alignment in rows["alignment_manifests"]:
        path=alignment["input_path"]; children=caps[path]
        if canonical_repo_id(alignment["repository"]) != alignment["repo_id"]:
            _fail("CATALOG_ROWS_INVALID", "/tables/alignment_manifests", "alignment repo identity differs")
        if len(children)!=5 or {x["name"] for x in children}!=names or {x["ordinal"] for x in children}!=set(range(5)):
            _fail("CATALOG_ROWS_INVALID", "/tables/alignment_capabilities", "alignment lacks five capabilities")
        if alignment["officiality"]=="official" and not official[path]:
            _fail("CATALOG_ROWS_INVALID", "/tables/alignment_officiality_evidence", "official alignment lacks evidence")
        for child in children:
            key=(path,child["name"])
            if child["status"] in {"present","partial"} and not locs[key]:
                _fail("CATALOG_ROWS_INVALID", "/tables/alignment_capability_locators", "capability lacks locator")
            if patterns[key] and child["absence_scope_present"] != 1:
                _fail("CATALOG_ROWS_INVALID", "/tables/alignment_absence_patterns", "patterns lack scope")
        document={"schema":alignment["schema"],"paper_id":alignment["paper_id"],"repository":alignment["repository"],"commit":alignment["commit"],
                  "officiality":{"status":alignment["officiality"],"evidence":[decode_ledger_locator(x["locator_wire"]) for x in sorted(official[path],key=lambda x:x["ordinal"])]},
                  "license":{"spdx_id":alignment["license_spdx_id"],"notes":alignment["license_notes"]},"archived":bool(alignment["archived"]),"capabilities":[]}
        for child in sorted(children,key=lambda x:x["ordinal"]):
            key=(path,child["name"]); item={"name":child["name"],"status":child["status"],
                "locators":[decode_ledger_locator(x["locator_wire"]) for x in sorted(locs[key],key=lambda x:x["ordinal"])]}
            if child["absence_scope_present"]:item["absence_scope"]={"commit":child["absence_commit"],"tree_prefix":child["absence_tree_prefix"],"search_patterns":[x["pattern"] for x in sorted(patterns[key],key=lambda x:x["ordinal"])]}
            if child["checkpoint_kind"] is not None:item["checkpoint_kind"]=child["checkpoint_kind"]
            document["capabilities"].append(item)
        _closed_schema(document,"video-paper-wiki.paper-code-alignment.v1","/tables/alignment_manifests")


def _validated(generation_material: object, tables: object) -> tuple[dict, dict, dict[str, list[list]]]:
    _safe_preflight(generation_material, tables)
    manifest, profile = _resources()
    try:
        generation_hash = projection_generation_sha256(generation_material)
    except ContractError as exc:
        if exc.code in {"PROJECTION_LIMIT_EXCEEDED", "CATALOG_RESOURCE_MISMATCH"}: raise
        raise ContractError("PROJECTION_GENERATION_INVALID", "generation material is invalid", exc.details) from None
    assert type(generation_material) is dict
    rows, raw, positions = _row_maps(manifest, tables)
    _relational(manifest, rows, positions)
    try:
        _semantic(manifest, generation_material, rows)
    except ContractError as exc:
        if exc.code == "CATALOG_ROWS_INVALID":
            raise
        _fail("CATALOG_ROWS_INVALID", "/tables", "catalog semantic closure is invalid")
    except (IdentityError, KeyError, TypeError, ValueError):
        _fail("CATALOG_ROWS_INVALID", "/tables", "catalog semantic closure is invalid")
    # The packaged fixed resources must be the same bytes declared by generation.
    resources = {x["path"]: x["sha256"] for x in generation_material["resources"]["files"]}
    bindings = profile["bindings"]
    for logical, expected in ((bindings["ddl_resource_path"], _DDL_SHA),
                              (bindings["column_manifest_resource_path"], _MANIFEST_SHA),
                              (bindings["profile_resource_path"], _PROFILE_SHA)):
        if resources.get(logical) != expected:
            _fail("CATALOG_ROWS_INVALID", "/generation_material/resources", "catalog resource declaration differs")
    return manifest, {"generation_sha256": generation_hash}, raw


def canonical_catalog_rows(*, generation_material: object, tables: object) -> bytes:
    manifest, bound, raw = _validated(generation_material, tables)
    definitions = {x["name"]: x for x in manifest["tables"]}
    output = []
    for name in sorted(definitions):
        definition = definitions[name]; columns = [x["name"] for x in definition["columns"]]
        indexes = [columns.index(x) for x in definition["primary_key"]]
        def key(row):
            return tuple((0, row[i]) if type(row[i]) is int else (1, row[i].encode("utf-8")) for i in indexes)
        output.append({"name": name, "columns": columns, "rows": sorted(raw[name], key=key)})
    return canonicalize({"schema": "video-paper-wiki.catalog-rows.v1", "ddl_sha256": _DDL_SHA,
                         "generation_sha256": bound["generation_sha256"], "tables": output})


def catalog_rows_sha256(*, generation_material: object, tables: object) -> str:
    return hashlib.sha256(canonical_catalog_rows(generation_material=generation_material, tables=tables)).hexdigest()


__all__ = ["canonical_catalog_rows", "catalog_rows_sha256"]
