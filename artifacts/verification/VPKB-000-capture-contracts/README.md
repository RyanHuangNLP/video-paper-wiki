# VPKB-000-capture-contracts local verification

Recorded 2026-09-01 against the stable working-tree candidate based on
`65c279f3dac280f1046c08536f59887b0dc613c7`. This record precedes the delivery commit;
it intentionally does not claim that baseline SHA contains the new implementation.
Contract revision 2 SHA-256:
`d54e1c36608ca0d57c0ea467f208a9645259ff2c879f23958a58c2280ed9e23d`.

The capture inspection and code manifest schemas, pure byte/locator validators,
and proposal → inspection → inspected-manifest bindings passed local Architect
acceptance. Non-string root keys and cyclic hash inputs now refuse through the
new contract boundaries; existing common schema, identities and JCS are unchanged.

| Check | Observed result |
| --- | --- |
| macOS arm64 / Python 3.12.14 full suite | 899 passed; 0 failures/errors/skips; 71.02s; exit 0 |
| macOS arm64 / Python 3.13.13 full suite | 899 passed; 0 failures/errors/skips; 68.35s; exit 0 |
| Independent Steward tests / Python 3.13.13 | 45 passed; 0 failures/errors/skips; 0.04s; exit 0 |
| Additional malformed-key/cyclic-material probes | 33 passed |
| Installed wheel outside source imports | 14 schemas; known hash graph; locator success/refusal; 1365 texts and 8116 line ranges; doctor exit 0 |
| Source stability | 257 source/input files identical before/after final full tests and wheel verification |

[local-results.json](local-results.json) contains exact arguments with personal
paths replaced by documented environment aliases, interpreter details, original
log/JUnit SHA-256, parsed JUnit counts, wheel/script digests, and all 257 source
hashes. Retained stdout: [Python 3.12](python312.log), [Python 3.13](python313.log),
and [independent tests](independent.log). Raw JUnit host metadata is not published.

The source snapshot is
`4fb11baa15eb303b9fc223b4b49ff93a05d93b53b080ce4f825d5b874eb18752`.
After committing, compare every recorded path to the committed blob before
binding the commit to these results. Evidence and changing handoff documents are
not included in the test-source snapshot, so no evidence self-hash cycle is made.

The first sandboxed Python 3.13 full run reported 894 passed and five AF_UNIX bind
permission failures. The final replay allowed those local sockets and passed all
899 without skips or weakened tests. The first wheel doctor smoke correctly
refused WORKSPACE_ROOT_INVALID outside a checkout; the successful smoke asserted
that refusal and used an isolated minimal checkout for doctor success. This was
a test setup adjustment, not a product fix.

Replay full tests with the locked default environment and the short real temp
recipe in the root [README](../../../README.md). No operator, Docling extra or
parser model is needed. Immutable packaged-schema loading is allowed; tests of
supplied-data operations warm the registry before intercepting I/O. This does
not establish OS-level egress isolation or any production upstream/Vault behavior.

New-candidate remote CI is pending. Store the subsequent current head/base,
actual checkout SHA, run/attempt and required jobs separately (PR delivery note
and local CI observation), without relabelling earlier runs. Local acceptance
is not merge permission. PR #94 remains draft → integration; VPKB-000, human
gates, engine-mvp and corpus-v1 remain unclosed. No real source-ID derivation,
sibling enumeration, no-follow/locking/concurrency or Vault transaction was tested.
