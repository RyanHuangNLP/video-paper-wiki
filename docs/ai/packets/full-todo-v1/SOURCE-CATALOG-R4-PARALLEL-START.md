# SOURCE-CATALOG R4 — isolated implementation while predecessor CI runs

Architect coordination amendment: R1/R2/R3 interfaces, profile bytes and the
17-path allowlist remain unchanged. R1's implementation-start prerequisite may
be satisfied by the exact committed SOURCE-CONVERSION R2 snapshot after its
independent reviews, both locked full suites and actual installed-wheel checks
have passed and Architect has issued local acceptance. Bind that exact commit
and its parent/tree in the new catalog freeze; do not use an anticipated SHA.

Catalog implementation then runs in a separate independent clone. It cannot
write the conversion candidate, delivery checkout or any already reviewed
conversion source. Only root owns the catalog's 17 implementation paths.
Steward retains serialized Git/PR/CI authority. No external Builder starts.

Predecessor fresh CI and separate exact-head acceptance remain mandatory before
catalog delivery or SOURCE completion. If that CI fails and conversion needs
repair, the catalog delivery pauses until a reviewed rebase/integration and new
baseline binding; its old freeze and evidence remain historical. Local acceptance
is not relabelled as remote CI or exact-head acceptance. This amendment permits
independent work while CI runs and does not relax any product validation, real
Vault restriction, human gate, no-PDF rule or no-merge boundary.
