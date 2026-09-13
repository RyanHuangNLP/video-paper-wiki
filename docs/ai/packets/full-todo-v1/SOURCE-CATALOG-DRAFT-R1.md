# SOURCE catalog — concrete successor draft

Review draft only; implementation waits for a frozen contract and exact accepted
SOURCE-PUBLICATION baseline. Keep all closed base/search catalog v1 schemas, SQL,
column manifests and generation profiles unchanged. The new explicit profile is
source-catalog-v1. Existing legacy index.status must preserve the specific
SOURCE_PROFILE_REQUIRED refusal from its collector rather than erase the code.

## Read-only current-state authority

Build, status, query and citation resolution each retain all Vault ancestor edges,
then use one _Snapshot for audit_integrity, collect_source_state(require_rendered=True),
complete inventory and the raw bytes needed for citations. The collector must not
filter semantic paths through the old _kind function. Every success and exception
rechecks complete inventory and named edges, including failed enumeration.

Use a separate deterministic catalog artifact staged only under
.work/<batch>/source-catalog/catalog.json. It contains source-catalog-v1 profile,
current basis, generation material and complete projection rows. This is a
replaceable cache, not another mutable canonical ledger. Stage one fixed private
file with retained absent/present slot and create/reuse behavior; no arbitrary
output paths or Vault mutation. No external index/server dependency is needed.

Generation binds the complete current inventory (path/hash/size/mode, including
head, receipts and historical source snapshots), the new profile resource,
canonical schemas/taxonomy, relevant compiler/collector/query implementation
bytes and exact runtime/dependency/tokenization profiles. Full rows and their
ordering also participate in the catalog digest. Freeze the precise material and
limits before implementation; never omit files or rows to fit a limit.

A loaded cache is never trusted merely because it names the current basis.
Reconstruct its canonical projection from retained source bytes and require exact
catalog equality. This refuses invented rows/excerpts even when a caller computes
self-consistent descriptor hashes. A changed live basis/profile makes a previous
catalog stale. Status is evidence-derived; an unclaimed capture or registered
source without a canonical paper remains visibly uncovered, not silently dropped.

## Projection and user behavior

Include all canonical papers (legacy/v2), repositories, claims and ownership,
assessment events/heads, source registrations and associations, display decisions
and heads. Preserve legacy evidence wire strings and raw optional-key spelling in
source material; project only a new explicitly declared closed format. Do not
reuse base-catalog presence columns with changed meaning.

Each result distinguishes the selected display association from each citation's
actual referenced association. A citation to a historical version remains valid
when its bound bytes/history exist; display selection alone does not label it
stale. Markdown resolution returns the exact Unicode source span, page anchor,
excerpt/hash, source ID and association identity. Code/PDF legacy resolution must
use their actual retained capture/parser/manifest data and established locator
semantics; unsupported resolution is explicit, never fabricated text.

Queries support exact identity/title lookup and deterministic lexical ranking of
claim text and source excerpts, with explicit paper/assessment/lifecycle filters.
Provisional claims remain visibly provisional. Accepted-only filtering never
promotes model claims. Query results carry catalog generation and current basis;
query/resolve validate these again before returning. Freeze ranking, tie order,
query/result limits and the public response schemas. Reuse existing deterministic
tokenization where compatible, without altering old query behavior.

Required continuous tests: empty, fully rendered legacy, Markdown and mixed
catalogs; exact citation resolution and tampering; selected vs referenced version,
explicit selection/rollback; claim invalidation/review fixtures; unchanged builds,
current/stale generation, closed filters/limits; partial-catalog forgery; unknown
semantic paths and success/failure lineage changes. Existing synthetic backup and
isolated restore should reconstruct the same canonical catalog generation where
runtime/profile is unchanged. No real Vault, operator or human gate is closed.
