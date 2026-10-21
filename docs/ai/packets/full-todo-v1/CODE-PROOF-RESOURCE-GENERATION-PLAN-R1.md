# CODE resource generation plan — draft, not dispatched

This prepares the bounded resource prerequisite required by R12. It does not
start another Builder, freeze a baseline, accept CONFIG, or authorize a source
write. The active Builder remains the CONFIG repair. A final packet, exact input
manifest, resource-generation invocation and Architect handoff must follow the
accepted CONFIG commit and independent review of this plan.

## Product paths and ownership

The generation increment will own exactly fourteen product paths in the CODE
worktree. Grok authors the resource content and resource test implementation.
Independently prepared fixture material may be copied/packed mechanically only
under an explicit reviewed integration amendment.

Eleven new resources are the ten schema filenames listed in
`CODE-PROOF-RESOURCE-CONTRACT-R12.md`, under checkout `schemas/`, plus
`src/video_paper_wiki/profiles/code-proof-v1.json`. The remaining paths are:

- `tests/contract/test_code_proof_resources.py`, a new resource contract suite;
- `tests/fixtures/code-proof-resource-v1.json`, a new deterministic case bundle;
- `tests/contract/test_schemas.py`, only its existing schema-count assertion
  changing from 71 to 81 after all ten new schemas are actually present.

The final freeze must verify the three proposed test paths against the accepted
baseline and preserve all 71 existing schema bytes. No package metadata change
is needed merely to add these resources: the existing package inclusion rules
already cover the new profile directory and schema files. Verify the resulting
wheel, rather than changing those rules speculatively. No public command, CLI
registration, loader, retained-I/O implementation or legacy schema belongs to
this increment.

## Required inputs and output form

The final inputs must include R4 identity/layout, R7 wire shapes, R9 public
closure, R10/R11 cap disposition where it affects resource admission, R12,
both accepted kernel result contracts, and exact accepted examples. Bind all
input bytes. CONFIG examples must be derived only after its candidate has been
accepted; the presently rejected parser is not a trusted fixture producer.

Use the existing source-only, raw SHA-1/SHA-256 and normalized wire fixtures,
their accepted correction records, and the separately reviewed pending/partial
examples. Include typed JSON and TOML config evidence with the full accepted
kernel result, not a fabricated reduced result shape. Review required positive
coverage before dispatch; unavailable cases remain explicit prerequisites.

A compact Grok-authored generator may be used instead of repeating equivalent
schema definitions in a large textual response. If selected, its complete
source must first be returned, inspected and frozen as an evidence artifact.
Its sole writable output is a fresh staging directory containing the named
resources; it must refuse preexisting outputs and perform no network, Git,
subprocess, dynamic-code or repository discovery operation. Local execution of
such a reviewed generator is a mechanical resource-generation step, not a
substitute for Grok authorship or resource review. The final invocation chooses
and freezes one output form; this draft does not choose a runtime or launch it.

## Deterministic fixture bundle

The test bundle has a closed top-level object:

```text
{schema, profile_sha256, cases}
```

`schema` is `video-paper-wiki.code-proof-resource-fixtures.v1`.
`profile_sha256` identifies the actual generated profile bytes. Each case is
closed `{name, title, instance}` with a unique ASCII name and a title from the
ten-resource inventory. Cases are sorted by name. This is a test transport
format, not an eleventh public schema or a saved ce1 envelope.

After schema/profile generation, rebuild profile-bound fixtures and all their
ce1 IDs/references using the actual profile hash. Do not replace placeholder
digests in serialized strings. Ordinary request inputs retain no profile-hash
field. Fixture packing must preserve each instance's values and must not convert
floats, repair strings or normalize source text. Include a small separate
profile-validation case in the suite by selecting common `$defs/profile`;
the profile itself is not wrapped as a ce1 document.

The positive coverage inventory includes all six saved envelope kinds, both
ordinary input schemas, all five successful command data payloads, each pending
status, incomplete raw target sets, normalized other outcomes, source-only and
typed JSON/TOML configs, and both Git object formats. A completed but ineligible
observation is a valid positive fixture, with no fabricated handoff. A valid
configuration target can remain usable when a different target is missing.

## Verification requirements

Resource tests must load the exact ten resource names into an explicit fresh
registry with retrieval denied for any undeclared resource. Check Draft 2020-12
validity, root `$id`/title/dialect, resolvable reference fragments, prohibited
nested IDs/anchors/dynamic references, nested closed shapes and all R12 profile
constants and inventory hashes. Use an exact-int type checker so bool, float
1.0 and int subclasses cannot pass as integers. Public API builtin-type and
byte-budget checks remain separate later requirements.

Respect the difference between JSON Schema character lengths and UTF-8 byte
caps. A schema can provide a necessary character bound; it cannot claim that
this proves a non-ASCII string fits the byte cap. Likewise lexical OID validity
does not prove consistency with a selected Git object format. Keep structural
checks distinct from semantic replay and retain the reviewed negative-case
errata that preserve deliberately corrupted IDs/references.

Structural negative tests must exercise unknown and omitted fields, wrong ref
kind, strict integer failures, excess collections, impossible mode/state nulls,
and malformed nested kernel-result nodes/declarations/targets. Start mutations
from a validated positive instance and assert the expected rejection. Do not
weaken the schema because a positive fixture has incorrect provenance or
derivation; diagnose and preserve that failed fixture instead.

After the Builder stops and all product bytes are frozen, independently verify
the resource inventory, profile hashes, positive/negative structural tests,
reference closure, byte formatting and old-schema preservation. Build an
isolated wheel with the existing locked environment and prove every generated
schema/profile file is packaged byte-for-byte at the required imported-package
locations. Apply the 71-to-81 test assertion only as the reviewed integration
change, then run the appropriate regression suite on both locked Pythons.

This increment can establish resource correctness and packaging. Semantic
saved-byte/identity/replay tests, retained-I/O fault handling and actual command
behavior still require the following public implementation. No resource-only
acceptance completes CODE, closes a human gate, or authorizes a Git push/merge.
