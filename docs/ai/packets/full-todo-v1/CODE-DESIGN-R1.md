# Official code and configuration continuation — design R1

Design only; no Builder file ownership or implementation dispatch. This records
Repo Steward's inspection of the accepted 62e05c0 baseline and Architect's scope
choices. It preserves code capture, source/claim ledgers and all closed v1 schemas.

The existing code boundary already validates strict UTF-8, normalized line/snippet
hashes, repository/full commit/path and manifest identity. Retained staged code
capture creates or reuses a content-addressed `.bin` through pinned generic
transaction inspection. It does not prove that a repository is official or that
caller-supplied source bytes came from that Git commit. Existing alignment v1
supports PDF-only officiality evidence and cannot accept arbitrary web URLs.

The missing user flow is: paper/source-version selection → bounded official-code
observation requests → actual connector observations/local source byte inputs →
commit/config/capability evidence proposal → independent relation review → canonical
publication handoff. Public Python remains zero-egress. This packet must not add
an agent-side GitHub fetcher or run/install vpwiki-admin. A request/observation
contract lets the host connector or an external operator provide bytes/evidence;
transport details that the connector cannot expose remain unknown.

Proposed own `code-observation-request.v1` binds paper ID, optional exact source
association, canonical repository, explicit full commit and role-grouped file
paths. Roles include README, CITATION, license, implementation, configuration and
entrypoint. Each target is an explicit bounded URL/path request, never an arbitrary
shell command, archive fetch, clone or recursive monorepo traversal. Budgets cap
requests, per-file/total bytes and item counts. Requested transport constraints
are distinct from verified observations. Git commit/tree/blob identifiers and
normalized text SHA-256 have different meanings and must not be substituted.

The actual observation is immutable and hashes the request reference, observed
repository/commit/tree/file facts, exact text/bytes capability and the source
excerpts. It distinguishes Git-verified local source input from normalized web
content; a normalized view cannot manufacture byte-exact source authority. Local
file bytes enter the existing code capture through an explicit source-file handoff.
One manifest remains bound to one logical origin path. A multi-file collection
references those independent captures and fixes one repository/commit across the
collection; missing files stay missing and partial collections stay partial.

Officiality is a relation-review successor, separate from discovery signals:

- A: the paper explicitly presents this repository as its implementation.
- B: a paper-linked project page explicitly identifies the implementation.
- C: repository README/CITATION precisely refers back to the paper.
- D: independently evidenced author/control identity and explicit declaration.

A/B plus C is a preferred evidence combination, not a mandatory C rule. C alone,
same organization, similar names or a baseline/dependency link cannot establish
officiality. A reviewed direct release without reverse link may be official with
its evidence gap and reason recorded. Explicit third-party reproduction supports
unofficial; insufficient evidence remains unverified_candidate. A model proposal
never issues the human relation review or upgrades canonical officiality.

Capabilities cover training, inference, preprocessing, evaluation and checkpoints.
Every present/partial proposal cites exact source/config lines or a clearly marked
README-only statement. Absence requires a declared search scope and observed file
inventory; an unfetched path is unverified. Checkpoint URL/revision/license metadata
is permitted; no weights are downloaded. Config interpretation is data-only with
closed supported formats, no imports, YAML object constructors, scripts or model
loading. Mismatch proposals bind both exact sides (paper↔repo, README↔config,
main↔appendix or version↔version), conditions and version labels; they do not
change an assessment automatically.

Canonical relation records must join the existing inspected code manifests,
source IDs, paper/source association and the accepted review under one receipt-
backed publication. New namespaces need explicit prospective validation, audit,
catalog and backup coverage. Do not manufacture PDF locators to satisfy alignment
v1; introduce a compatible successor with a deliberate legacy refusal policy.
Display-head changes do not retarget existing code evidence or reviews.

Freeze acceptance after actual SOURCE interfaces settle. Required engineering
cases include repository/commit/path mismatches, CRLF/raw-hash distinction,
normalized-only capability gaps, duplicate content at distinct logical paths,
partial multi-file inputs, hostile paths/JSON/configs, fake officiality shortcuts,
legitimate direct-release-without-backlink, bounded absence, cross-side mismatch,
source-version change, and zero-egress/no-Vault-write sentinels. Actual official
repository trials and human relation judgments are separate recorded outcomes.
