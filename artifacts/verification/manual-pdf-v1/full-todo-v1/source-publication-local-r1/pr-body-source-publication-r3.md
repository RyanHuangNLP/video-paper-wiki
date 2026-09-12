## Summary

Add the source-aware publication prepare, inspect, and audit flow on top of the existing paper preview and version-aware source semantics work. The delivery adds the closed publication request, proposal, authority, and assessment-head schemas; receipt-backed source-state validation; retained prepare/inspect lineage; structured error propagation; and the three source-publication CLI leaves.

The existing preview integration and source-semantics behavior remain in the branch. Legacy v1 behavior and the existing command tree are preserved while source-aware publication gets its own typed path.

This draft is delivered as the exact 87-path snapshot at commit `fb37dcd80fa4445d86872a9e03ecb6a720048596`, based on `c32e68d08a142d5a5559ce717ff397f9b27f55d1` and targeting `integration`.

## Validation

- Python 3.12 local suite: `3285 passed`.
- Python 3.13 local suite: `3285 passed`.
- The mixed legacy/v2 fixture covered 57 files, 4 papers, 1 repository, 4 claims, 7 events, 6 compiled pages, 1 association, and 2 ledger snapshots.
- The isolated Hatchling wheel check passed with 69 schemas and byte-parity checks for the packaged resources and source-publication modules.
- The exact delivery audit verified all 86 payload files plus the manifest self path, cached exactly 87 paths in a temporary index, and passed `git diff --cached --check`. The full delivery tree contains no PDFs; the 67-paper seed, vendor pin, and overlays remain unchanged.

Fresh exact-head CI run `34318336303` passed all four Linux/macOS × Python 3.12/3.13 jobs, each reporting `3285 passed`, against merge preview `e209c35a1c860cc2ce304bdfb9ec107e28850ff4` with base `08709894adfb20ec07e976783f0ba436d975b74f` then head `fb37dcd80fa4445d86872a9e03ecb6a720048596`. The CI result does not substitute for exact-head Architect acceptance.

## Scope and remaining work

SOURCE conversion and the source-aware catalog/query/retrieval work remain subsequent TODOs. Real-data intake, Vault/operator apply, human review, and merge gates remain open. This PR does not claim roadmap completion.

The delivery remains a draft PR targeting `integration`; no merge or automerge is requested.
