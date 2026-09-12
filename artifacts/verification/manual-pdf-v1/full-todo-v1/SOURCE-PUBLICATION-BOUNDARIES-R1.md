# SOURCE-PUBLICATION boundaries, revision 1

**Review mode:** read-only architecture boundary review; no source, Git, Vault, network, or external-runtime mutation.

**Frozen inputs:** `SOURCE-SEMANTICS-R2.md` SHA-256 `ad21572558bf1053a248f07d5bb3e950780765aecb8ed4ef4da29025047366f9`; `SOURCE-SEMANTICS-LEGACY-BBOX-R3.md` SHA-256 `f1196fe43f815d388acb3359d75a045eca10643539ca0869065a09b81addd5b1`; R3 freeze SHA-256 `3fc048e58b9e3a32b2861335d466ed431229a9afffd71af66a4b1cd4735b3129`.

The repository's conceptual `catalog.py` and `integrity_audit.py` boundaries are implemented by `catalog_collector.py`/`catalog_store.py` and `receipt_audit.py`. The continuation must use those existing retained-I/O seams rather than inventing a second Vault reader.

## Existing authority boundary

`receipt_audit._Snapshot` is the reusable retained Vault authority. It opens the Vault root no-follow, retains descriptor-relative parent and file edges, records bytes/stat stamps, and rechecks named edges, absent paths, the mutation lock, and the complete inventory (`src/video_paper_wiki/receipt_audit.py:46-130`, `:130-190`, `:245-250`). `audit_integrity(..., _snapshot=snap)` must run first; it validates the head, exact receipt bytes and filenames, contiguous reachable sequence, replay preconditions, managed complete set, and ever-claimed raw bytes (`receipt_audit.py:267-345`). It is read-only and returns receipt/head/current-path authority; it does not authorize a human or operator.

Publication already creates one `_Snapshot`, audits it, reads all declared inputs through that snapshot, runs prospective validation, emits the receipt/head proposal, and verifies the snapshot before returning (`publication.py:331-375`, `:393-442`). `inspect_publication` repeats the request/input-tree and snapshot checks around success and every exception (`publication.py:493-538`). This is the smallest safe transaction boundary: source-state collection must occur inside this same retained snapshot and before prospective graph/render checks. Do not reopen the Vault by path between audit and collection.

Catalog collection follows the same pattern: `collect_current_catalog_material` creates one `_Snapshot`, audits it, walks the inventory, reads every selected byte through the snapshot, and returns the retained snapshot only with `_retain=True` (`catalog_collector.py:160-175`, `:210-237`). `catalog_store.catalog_status` retains both the catalog database and the live collector snapshot, derives live metadata, executes a barrier, then verifies both retained authorities before comparing digests (`catalog_store.py:582-631`). The source-semantic state digest must be added to this same retained comparison if catalog freshness depends on it.

## Complete managed namespaces

`receipt_audit` currently treats these as managed and therefore receipt-replayed: `.raw/captured/**`, `.raw/derived/**`, `wiki/papers/**`, `wiki/code/**`, `wiki/concepts/**`, `wiki/meta/ledgers/**`, `wiki/meta/records/**`, `wiki/meta/reviews/**`, `wiki/meta/gates/**`, and `wiki/meta/operations/**`, plus exact `wiki/meta/registries/operation-head.json` and `wiki/meta/registries/gate-heads.json` (`receipt_audit.py:19-26`, `:220-242`). This broad audit namespace is the complete-set tamper boundary.

The frozen base projection admits only the exact 13 input branches: two ledgers, taxonomy, paper records, repo records, assessment events, captured artifacts, Docling document/config/model siblings, run manifests, code manifests, and alignment manifests (`projection_input.py:19-34`; `docs/ai/contracts/projection-input-v1.md:77-103`). It explicitly excludes Markdown pages, `.vault-meta`, notes, staging, gate/operation registries, receipts, mutable assessment-head registries, generated chunks/BM25, and SQLite from the base input (`projection-input-v1.md:100-103`). The existing collector filters inventory through `_kind` and therefore silently leaves any future source-semantic path outside those 13 branches out of its base material (`catalog_collector.py:29-36`, `:168-175`). That omission is acceptable only if the continuation collects and hashes the source-semantic namespace separately; it must never imply that the audit did not see those files.

The frozen SOURCE-SEMANTICS paths that publication must recognize as a version-aware extension are:

| State | Canonical path namespace | Required treatment |
| --- | --- | --- |
| Source-version association | `wiki/meta/records/source-versions/<sva-...>.json` | Read exact bytes, validate the full v1 association object, recompute ID and object SHA, and retain every version. |
| Display decision chain | `wiki/meta/reviews/source-display/<svd-...>.json` | Read exact bytes, validate links/sequence/actor/choice, and retain every decision. |
| Display-head registry | `wiki/meta/records/source-display-heads.json` | Treat as a derived complete registry: recompute from every decision and compare exact selected-paper set and bytes. |
| Existing paper records | `wiki/meta/records/papers/<name>.json` | Admit v1 and v2 by explicit version dispatch; do not upgrade v1 bytes or identifiers. |
| Existing claim ledger | `wiki/meta/ledgers/claim-ledger.json` | Preserve exact legacy object/bytes and event evidence prefix. |
| Existing assessment events | `wiki/meta/reviews/<clm-20hex>/<ase-20hex>.json` | Preserve the complete v1 event prefix; a v2 successor must link the actual v1 terminal event. |
| Registration snapshots | `.raw/derived/source-ledgers/<sha256>.json` | Include every association's exact historical ledger snapshot; do not substitute current ledger bytes. |
| Raw/extraction material | `.raw/captured/<sha256>.md`, `.raw/derived/markdown-source/<raw>/<observation>.json` | Use the exact association-declared paths and complete maps; aliases share one map entry. |

These names are semantic roles, not permission to add a generic `wiki/meta/**` reader. Every path must pass the existing portable/NFC/casefold and receipt audit checks. Unknown files under a managed prefix remain an out-of-band/complete-set concern; unknown source-semantic files must be reported or refused rather than silently ignored.

Publication request paths already allow the managed business/read prefixes and exclude operation receipts/head from caller reads (`publication.py:70-94`). Transaction business policy allows `.raw/derived/**`, `wiki/meta/ledgers/**`, `wiki/meta/records/**`, `wiki/meta/reviews/**`, `wiki/meta/gates/**`, the paper/code/concept trees, and `gate-heads.json`; captured files are create-only capture business (`transaction_contracts.py:114-136`). The continuation must keep operation head and receipt paths publisher-owned and appended last (`publication.py:393-408`, `transaction_contracts.py:233-240`).

## Version-aware collection contract

The collector should expose one retained-snapshot result to both publication and catalog, with the exact shape frozen by the root architecture. The minimum contents are:

1. The audited receipt/head result and immutable inventory set from `_Snapshot`.
2. Exact path-to-bytes entries for every recognized source-semantic path, read only through `_Snapshot.read`, with path, SHA-256, and size retained.
3. Parsed association objects, historical source-ledger snapshots, display decisions, derived display heads, paper records, claims, and assessment events partitioned by v1/v2 schema.
4. The complete immutable v1 prefix for every claim history and its terminal event identity/profile/fingerprint before considering proposed v2 successors.
5. A deterministic source-semantic generation digest over canonical path/hash/size records and the validated semantic projections. This digest must be carried into catalog generation/meta and into publication's prospective transaction material.

Collection phases should be ordered as: (a) audit/complete-set and exact path classification; (b) bytes and closed-shape/schema validation; (c) per-object identity/reference checks; (d) complete source inventory/registration proofs; (e) event/display derivation and immutable-prefix checks; (f) v1/v2 compiler input assembly. A malformed object must not be allowed to become a missing/orphan result, and a current ledger must not stand in for a missing historical registration snapshot.

For publication, merge proposed payload bytes with the retained current state in memory only, then run the source-version inventory and compiler against that merged view. The receipt/head proposal must include every new or replaced source-semantic byte as ordinary business writes; the publisher must compare the retained current bytes again before returning. Generic capture remains `receipt=null`, `head=null`, `claimed_inputs=[]`; it is an orphan until a later ingest receipt claims the exact captured path/hash. Do not synthesize a capture receipt or relabel an old raw-create receipt as Markdown registration (`SOURCE-SEMANTICS-R2.md:300-306`).

For catalog, collect from the same audited snapshot that feeds the base rows. The source-semantic digest is a separate authority input from the existing 13-branch projection inventory, while the catalog generation must bind it so a new association/event/display decision cannot leave the search catalog appearing current. `catalog_store.catalog_status` should compare the stored source-semantic digest to the live retained digest alongside `mapping`, `join`, `catalog`, and base-row digests (`catalog_store.py:605-616`).

## Preserved legacy behavior and refusal matrix

- v1 ledgers, v1 assessment event IDs/fingerprints, v1 locator wires, and v1 rendered bytes remain byte-identical. The R2 contract requires legacy-only delegation and exact bytes when no v2 paper is present (`SOURCE-SEMANTICS-R2.md:144-152`, `:188-210`).
- A v2 paper record may retain v1 metadata and old source associations, but publication must not silently convert a v1 record or claim that an unversioned PDF is an observed release (`SOURCE-SEMANTICS-R2.md:116-125`).
- A first v2 event must be an explicit `evidence_invalidation` successor to the actual v1 terminal event; direct v1-to-v2 human approval, v2-to-v1 reversion, dropped predecessor events, regenerated predecessor IDs, or altered predecessor bytes refuse (`SOURCE-SEMANTICS-R2.md:159-174`, `:315-321`).
- Association reuse requires the full prior object, exact registration proof, observation, extraction reference, and bytes. Same explicit key with changed bytes is `SOURCE_VERSION_CONFLICT`/exit 75; changed metadata is `SOURCE_PROVENANCE_VARIANT`/exit 75; duplicate IDs/keys or source ownership across papers refuse (`SOURCE-SEMANTICS-R2.md:70-90`).
- Display-head materialization must equal derivation from the complete decision set, including the complete selected-paper set; an import alone cannot create a decision (`SOURCE-SEMANTICS-R2.md:105-114`).
- The R3 exception permits finite exact Python floats only in optional four-coordinate PDF `bbox` arrays at declared evidence slots, including compiler code officiality evidence. It does not permit floats in association, display, event, record, ledger, catalog metadata, or arbitrary `kind:pdf` objects; nonfinite and fake-PDF placements refuse (`SOURCE-SEMANTICS-LEGACY-BBOX-R3.md:9-30`).

## Concrete adversarial scenarios

1. **Hidden source-version file:** add `wiki/meta/records/source-versions/sva-...json` after collection. `_Snapshot.verify()`/audit complete-set checking must fail or the source digest must be recomputed from the changed inventory; catalog status cannot remain current.
2. **Receipt-valid but omitted association:** publish an association write but omit it from the source-semantic map. Exact path/hash set equality and the generation digest must refuse the collection.
3. **Current-ledger substitution:** delete `.raw/derived/source-ledgers/<old>.json` while keeping the current source ledger valid. Registration proof must return `SOURCE_REGISTRATION_INVALID`; no current-ledger fallback is allowed.
4. **Legacy prefix rewrite:** replace a stored v1 event with a semantically equivalent regenerated object before appending v2. The collector must compare exact stored bytes/IDs and refuse the proposed successor.
5. **Fake PDF float:** place `{"kind":"pdf","bbox":[0.5,1.0,2.0,3.0]}` in a record/event/metadata field or Markdown evidence. Contextual preflight must return `SOURCE_SEMANTICS_INVALID`; only the four declared legacy PDF evidence branches admit finite bbox floats.
6. **Capture receipt fabrication:** add a synthetic receipt for a generic capture, or claim a capture as first registration without the later ingest operation and matching source-ledger write. Refuse as `SOURCE_REGISTRATION_INVALID`/receipt mismatch.
7. **Display-head fork/omission:** publish two decisions for one paper with a stale or partial `source-display-heads.json`. Recompute the complete chain and selected set; refuse rather than choosing one by path order.
8. **Cross-paper source reuse:** point associations from two papers at one source ID/raw hash. Source inventory ownership and association conflict checks must refuse.
9. **Catalog race:** mutate a page, source snapshot, or display decision between audit and row assembly. Both publication and catalog must use one retained `_Snapshot` and final `verify`; a reopened path read is insufficient.
10. **Unknown managed extension:** add a file under `wiki/meta/reviews/source-display/` or `wiki/meta/records/source-versions/` with an unsafe/case-colliding name. Receipt audit must reject it as unsafe/out-of-band, even if the base projection's `_kind` filter would otherwise omit it.

**Boundary conclusion:** reuse `_Snapshot` + `audit_integrity` as the sole retained Vault state core, add one version-aware source-semantic collector over that snapshot, and feed its immutable-prefix/complete-set digest into both publication prospective validation and catalog freshness. Keep staging retention (`_RetainedPublicationAuthority`) and disposable SQLite retention (`catalog_store._RetainedFile`) as separate file/transaction seams; neither replaces the audited Vault snapshot.
