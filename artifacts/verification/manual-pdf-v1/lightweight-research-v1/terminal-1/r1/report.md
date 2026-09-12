# T1 r1 — original/English lexical query fusion

Lane 1 Builder candidate against freeze `8b9b257080d01b69b4ea683728acfea9ba559c00a0292f4db034623e8e53c5a8` and contract `d1d1ddef4273e37b5f8e30a14ad22f3cb3e6c6fa9782763ed5544d20479f2fab`. Baseline remains `6963292a93ae322eaf9bb563b7b1170dee6a6fc6`. Architect has not accepted this candidate.

## Functionality

`light_query.py` adds public `export_rewritten_context(workspace_root, *, kind, query, rewrite, requirements="", paper_ids=None)`. `kind` remains `qa|writing`. The caller-supplied rewrite is exactly schema `video-paper-wiki.light-query-rewrite.v1` with `original_query` equal to `query` byte-for-byte, English `rewritten_query` (nonblank, ≤2000 characters, one Latin letter, no control characters), and `language="en"`. Invalid rewrite or query bounds return `QUERY_REWRITE_INVALID` without a `query_plan`.

Both the original question and rewritten English terms are searched with the existing BM25 algorithm, the same explicit paper selection, and one loaded index/source snapshot (`_search_same_snapshot`). Identical query strings collapse to a single `original` route. Each route keeps at most 24 candidates. Fusion is equal-weight RRF `sum(1/(60+rank))`, sorted by descending score then `chunk_id`, keeping at most 8 chunks. Evidence identity/text stay the live backend bytes; only the finite score becomes the fused rank. A stale, invalid, or unsafe route aborts with that closed backend status and never becomes `OK`/`NO_RESULTS`. Final live paper/index/slice validation is required even when both routes miss.

Successful and empty-miss results are ordinary `video-paper-wiki.light-context.v1` documents of the requested kind. `query` remains the original question. `query_plan` is diagnostic provenance (`video-paper-wiki.light-query-plan.v1`) and is not citation authority. Both-empty returns `status=NO_RESULTS`, `fused=[]`, `evidence=[]`, plus a valid trace; it is not importable. Other closed errors omit `query_plan`.

`validate_live_context` leaves legacy contexts without `query_plan` unchanged. When the field is present it uses a pure shape/RRF/hash checker plus live recomputation from the exact rewrite, then compares the whole trace and final evidence ids/scores. Caller-only hashes, boolean numeric impostors, unknown keys, and source drift fail closed. `_MANAGED_ROOTS` now includes `.light-writing`; import into that root raises `WORKSPACE_INVALID` and does not overwrite a user artifact.

Legacy `search()` ranking and return values are unchanged. CLI/Skill/`--rewrite` remain T3 integration work.

## Public result shapes

- `export_rewritten_context(...) -> light-context.v1` with optional `query_plan`
- `query_plan` keys: `schema, original_query, rewrite, rewrite_sha256, workspace_id, index_id, selected_paper_ids, paper_snapshots, fusion, routes, fused, plan_sha256`
- `fusion` is exactly `{algorithm:"rrf-v1", rank_constant:60, candidate_k:24, top_k:8}`
- rewrite-only success example: original `NO_RESULTS`, rewrite `OK`, `fused=[{chunk_id, score:0.01639344262295082, route_names:["rewrite"]}]`, context `query` stays Chinese
- both-empty example: `ok=false`, `status=NO_RESULTS`, `query_plan.fused=[]`, `evidence=[]`
- invalid rewrite example: `ok=false`, `status=QUERY_REWRITE_INVALID`, no `query_plan`
- `validate_live_context` success remains `{ok,status,index_id,workspace_root,message}`

T3 should call `export_rewritten_context` for workspace qa/writing `--rewrite` and keep using `validate_live_context` / existing qa/writing import. Do not edit T1 files.

## Files

Owned changed paths only:

- `src/video_paper_wiki_research/light_query.py`
- `src/video_paper_wiki_research/light_context.py`
- `src/video_paper_wiki_research/light_index.py`
- `tests/research/test_light_query.py`
- `tests/research/test_light_context.py`
- `tests/research/test_light_index.py`

## Tests

Pinned interpreter `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python` (3.13.13) with `PYTHONPATH` set to this worktree `src`. Official focused command exit 0: **63 passed in 0.37s**. Modules resolved to this SOURCE, not the old root checkout. No dependency install, no Git mutation, no Vault write, no model/network client.

## Unresolved issues

None that block this lane. T3 still owns CLI/Skill/docs, `--rewrite` wiring, and later integrated real-PDF/current-model trials. Architect still runs dual-Python full suites.
