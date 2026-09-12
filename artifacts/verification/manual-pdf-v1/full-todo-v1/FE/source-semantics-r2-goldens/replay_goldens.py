"""Focused replay of SOURCE-SEMANTICS R2 assessment and compiler goldens."""
from __future__ import annotations
import json
from pathlib import Path
from video_paper_wiki.assessment_history_v2 import derive_assessment_heads
from video_paper_wiki.canonical_compiler import compile_pages as compile_v1
from video_paper_wiki.canonical_compiler_v2 import compile_pages as compile_v2
from video_paper_wiki.contracts import ContractError
from video_paper_wiki.markdown_locator import resolve_markdown_locator
from video_paper_wiki.source_versions import derive_display_heads, validate_source_inventory
ROOT = Path(__file__).resolve().parent
def read_json(name): return json.loads((ROOT / name).read_bytes())
def authority_maps(association):
    receipt_bytes = {}
    for stem in ("receipt-1", "receipt-2"):
        value = read_json(stem + ".json")
        path = f"wiki/meta/operations/{value['sequence']:012d}-{value['operation_id']}.json"
        receipt_bytes[path] = (ROOT / (stem + ".canonical.json")).read_bytes()
    return {"raw_sources": {association["raw"]["path"]: (ROOT / "raw.md").read_bytes()}, "extraction_artifacts": {association["extraction"]["path"]: (ROOT / "extraction.json").read_bytes()}, "head_bytes": (ROOT / "head.canonical.json").read_bytes(), "receipt_bytes": receipt_bytes, "registration_ledgers": {association["registration"]["source_ledger_path"]: (ROOT / "ledger.canonical.json").read_bytes()}}
def main():
    results = []
    vectors = read_json("assessment-v1-to-v2-compatibility-vectors.json"); valid = vectors["migrated_valid"]
    assert derive_assessment_heads(claims=valid["claims"], events=valid["events"]) == valid["expected_heads"]
    results.append({"id": "V1_TO_V2_VALID_MIGRATION", "result": "pass", "head": valid["expected_heads"]})
    for case in vectors["negative_cases"]:
        try: derive_assessment_heads(claims=case["claims"], events=case["events"])
        except ContractError as exc:
            assert (exc.code, exc.exit_code) == (case["expected_code"], case["expected_exit_code"]), (case["id"], exc.code, exc.exit_code)
            results.append({"id": case["id"], "result": "pass", "code": exc.code})
        else: raise AssertionError(case["id"] + " unexpectedly accepted")
    association = read_json("association.json"); raw = (ROOT / "raw.md").read_bytes(); authority = authority_maps(association)
    validate_source_inventory([association], **authority); assert resolve_markdown_locator(read_json("locator.json"), association, raw) == "A verified Markdown conclusion."; assert derive_display_heads([association], [read_json("decision.json")])["heads"]
    results.append({"id": "SOURCE_INVENTORY_AND_LOCATOR", "result": "pass"})
    legacy = read_json("legacy-material.json")
    for path, data in compile_v1(legacy).items(): assert data == (ROOT / ("legacy-" + path.rsplit("/", 1)[-1])).read_bytes(), path
    results.append({"id": "LEGACY_V1_GOLDEN_BYTES", "result": "pass"})
    mixed = read_json("mixed-material.json"); actual = compile_v2(mixed, **authority)
    for path, data in actual.items(): assert data == (ROOT / ("candidate-" + path.rsplit("/", 1)[-1])).read_bytes(), path
    old = compile_v1(legacy)
    for path in ("wiki/papers/arxiv-2311.15127.md", "wiki/code/github-c75bb408b0db72b7f71083c4ed259711df47bf2fcb9d58ad813a095356f865bf.md"): 
        if path in old: assert actual[path] == old[path], path
    results.append({"id": "V2_MIXED_COMPILER_GOLDEN_BYTES", "result": "pass", "paths": sorted(actual)})
    print(json.dumps({"schema": "video-paper-wiki.source-semantics-r2-golden-replay.v1", "results": results}, ensure_ascii=False, sort_keys=True))
if __name__ == "__main__": main()
