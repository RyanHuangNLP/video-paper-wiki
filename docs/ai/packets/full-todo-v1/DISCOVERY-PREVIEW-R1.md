# DISCOVERY-PREVIEW R1: real paper previews with honest observations

This implementation slice adopts the complete behavior of
../../contracts/research-wiki-w1-preview-v1.md, SHA-256
`1ac864cc19e8080cba19d98b2157fd8d8ea59f277f361df4851dcfca05c864d3`,
with the explicit current-baseline changes below. Preserve that historical draft
byte-for-byte. This packet plus its freeze authorize implementation now; it does
not revive the historical Fable review schedule, two-agent topology or deadlines.
User: “把剩余的TODO都完成了吧，cursor grok的权限我都approve”.

Use the existing Astra + three Luna controllers, one pinned Cursor Grok Builder
per active isolated lane. Normal approval remains enabled. No Git by Builder,
new workers, real Vault/admin, PDF commit/download, model installation, or human
gate closure. Code and test fixture implementation are authorized; a recorded
fixture choice is never an actual user's decision.

## Current-baseline adaptations

1. The research package, CLI, common schema and manual-PDF storage already exist.
   Preserve them. Add new preview modules, schemas and a parser registration
   function called by the existing CLI. Do not replace cli.py, contracts.py,
   storage.py or common.v1 with the old from-scratch design. No dependency,
   pyproject/lock, engine schema or existing command behavior change is needed.
2. The W1 common resource is named `preview-common.v1.schema.json`; update its
   internal ID and the new schemas' refs accordingly. Keep existing
   common.v1.schema.json bytes unchanged. The other six schema filenames and
   envelope identities in the historical contract are new and retain their
   specified stems. New `preview_contracts.py` owns this registry, sealing and
   graph validation; it may reuse existing JCS, ResearchError and safe JSON
   parsing, but must not add preview kinds to the manual-PDF envelope registry.
3. Storage is `.work/research/<session>/preview-v1/` with the same five family
   directories `{requests,observations,metadata,proposals,decisions}`. All
   prescribed references and graph checks use this subtree. Existing manual-pdf
   sessions, lightweight workspaces and user notes remain separate and untouched.
   Implement `preview_storage.py` using existing low-level descriptor helpers;
   don't route through the manual-PDF-specific `open_research_session` layout.
   Bound JSON input depth before recursive decoding/validation where possible;
   catch parser recursion/Unicode/overflow with a stable refusal. Keep named
   ancestor and complete reference-graph checks on success and failure paths.
4. Public CLI remains the historical seven `paper ...` forms; add a small
   `register_preview_commands(subparsers)` function in `paper_preview.py` and a
   single integration call in existing cli.py. Existing _JsonArgumentParser and
   envelopes apply. Validate options/errors without unbounded traceback output.
5. Implement only the frozen `arxiv-abs-normalized-v1` page adapter. Byte-exact
   profile remains an explicit unavailable branch; no unused Atom executor or
   Python networking. Platform Web open belongs to the Skill/current session.
   Preserve unobservable transport fields as unavailable. The old CAP excerpts
   are incomplete and must fail metadata completeness, not become fake positives.
   Complete positive fixtures must be clearly synthetic. Live trial observations
   are recorded separately by Architect after implementation.
6. User selections remain explicit append-only decisions. The global instruction
   to complete development is not a selection of a particular paper/version.
   Source handoff contains exact decision/preview/metadata/observation refs and
   selected version; no claim of captured bytes, source registration or receipt.
   SOURCE-CAPTURE's declared version labels remain distinct from metadata proof.
   The later SOURCE-VERSION bridge must validate these references when assigning
   a verified arXiv version; this packet does not silently reinterpret labels.
7. This slice completes preview/request/decision engineering. W3 expansion,
   citation traversal, ranking, stop/checkpoint and multi-connector discovery are
   subsequent DISCOVERY work and cannot be declared done by this implementation.

## Structure and ownership

Builder owns only the exact freeze allowlist: new preview contracts/storage,
arXiv normalized-page parser and paper preview orchestration; seven new schemas;
one prompt template; focused tests; a concise preview Skill/manifest and user
quickstart; plus the small existing cli.py registration. No source files in the
SOURCE-CAPTURE lane are writable here. The two lanes have separate worktrees;
their two cli.py registration changes will be integrated and independently
reviewed serially. Do not copy another lane's live unreviewed changes.

Keep the Skill entrypoint focused: natural language requests to inspect an arXiv
paper or revisit a preview, request/cache, one official generated-URL open when
needed, truthful observation, current-model preview, render and actual selection.
Reference detailed formats only when needed. Follow skill-creator's guidance at
/Users/huangzhanpeng/.codex/skills/.system/skill-creator/SKILL.md; automatic discovery
stays enabled. The manifest documents the workflow, not an OS permission claim.

## Acceptance and stopped handoff

The historical contract's E cases apply with the above names/layout. Exercise
the actual public CLI with complete synthetic normalized pages and the preserved
incomplete CAP excerpts. Verify strict identity/version, named page sections,
submission history/latest_unknown, unavailable raw profile, cache TTL and policy,
prompt/model provenance, complete decision chains/conflicts, source-version
handoff refs, malformed input, limits, partial writes, all-exits lineage and
offline behavior. Do not write tests that merely assert documentation wording.
Bounded sample parsing must use named source sections; never guess bibliography
from footer links. Supported page rendering changes need explicit fixtures.

Run focused tests and preserve the final source hashes/candidate brief. Stop
writing after the candidate. Architect and an independent reviewer perform
acceptance, installed-wheel and full regression checks; fresh exact-head CI is
required after integration. Live preview and a user's actual choice remain
separate from fixtures. No merge or real operator application is authorized.
