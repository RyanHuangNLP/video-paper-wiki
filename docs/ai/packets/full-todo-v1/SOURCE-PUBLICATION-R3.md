# SOURCE-PUBLICATION R3 — precise legacy projection boundaries

Read with SOURCE-PUBLICATION-R2.md (SHA-256
908c94b376f5e130883acd332c7d9c12378daf2cd37b21507a16185dd58d5628).
This small successor overrides only the following field/profile distinctions.
R1/R2 drafts, reviews and rejected preparatory notes remain unchanged. Other R2
interfaces, four schema resources, authority rules and implementation paths stand.

The raw byte map retains every optional key's actual presence and participates
in basis hashing. The new typed collector does not reuse `_ledgers` to project
v2 evidence and does not change the frozen base-catalog tables or presence bits.
Its internal compiler claim shape has reviewed_at because that is the compiler
contract, not an assertion that upstream required the raw key.

For full rendered typed state and all knowledge prospective state, the local
claim row requires reviewed_at as a key whose value may be null; optional fields
are notes and supersedes. This retains projection-input-v1's closure. Pinned
ledger validation independently permits absent reviewed_at on nonaccepted claims.
The internal pure-legacy structural baseline branch may also read such absent
keys and expose null to its internal compiler-shaped object, while preserving
the unmodified raw bytes and presence. It cannot emit full typed audit success
or render authority from that branch; explicit knowledge migration must add the
reviewed_at key in proposed ledger bytes. Accepted claims require a valid date
in both branches. No new schema or base-catalog presence-bit change.

Local evidence is exactly `{source_id, relation, locator}` with a nonnull tagged
wire accepted by markdown_locator.decode_evidence (explicit legacy/v2 union).
Missing/null locators and extra keys fail structured local validation before any
indexing/row emission. Pinned ledger validation is looser about locator presence;
that does not create a locally usable citation. Wire relations are supports,
contradicts, context; decoded context is uncertain. Preserve occurrence order
and duplicates in the ledger; individual compiler/history validators retain
their existing rules rather than silently deduplicating.

Source enum domains come from the accepted historical_source_ledger projection:
origin kind file|url|manual; content_kind document|webpage|dataset|image|audio|
video|code|conversation|synthetic|other; authority official|primary|secondary|
community|synthetic|unknown; review_status unreviewed|active|superseded|rejected.
Synthetic content/authority pairing and all relational/date rules remain enforced.
Historical safe IDs keep `src-[A-Za-z0-9][A-Za-z0-9._-]*`, including src-paper.
New Markdown identity is the already frozen file+raw-path+content-digest formula,
never a hash of a mutable complete row. Existing full pinned inspection separately
enforces its stable_source_id formula and current-byte rules.

For v2 paper claims, location is closed `{path, anchor}` and the anchor must be
`^<claim-id>`: this is the versioned local compiler/page invariant, not an upstream
field rule. V1 paper and repository claims retain a closed location with required
path and optional/null/text anchor. Paths always bind canonical owner pages.
Actual declared nonempty anchors are checked against prospective pages by the
pinned inspector. V1->v2 migration must explicitly supply the v2 block anchor;
claim ID, owner and exact text remain unchanged. Knowledge cannot add repository
claims or refs in this increment. Existing base-catalog semantics are untouched.

The final freeze must bind this amendment, the immutable R2 bytes, exact allowlist,
source baseline/candidate, and recorded independent reviews. Pure consistency,
local tests, pinned inspection, remote CI and real human/operator acceptance remain
separate evidence categories.
