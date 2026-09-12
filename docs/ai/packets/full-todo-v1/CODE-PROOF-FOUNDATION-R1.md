# CODE private resource foundation — R1 preparation

Architect preparation for increment 1 of the public implementation sequence.
This is not a Builder dispatch or an accepted resource successor. The exact
resource commit and final pins must be added to a separate freeze after local
resource acceptance. R4–R12, the two accepted pure kernels, and the public
acceptance plans remain authoritative. The foundation boundary disposition
record resolves the earlier advisory's profile-registration and I/O ownership
ambiguities.

## Scope and ownership

Grok authors only the new module
`src/video_paper_wiki/code_proof_resources.py` and the new tests
`tests/unit/test_code_proof_resources.py`. Existing schemas, profile, fixtures,
kernels, CLI, dependencies and legacy resource loaders are read-only inputs.
There is no public CLI leaf in this increment.

The module selects a lexical resource-origin plan and compiles already retained
resource bytes. It never opens, reads, enumerates or writes a filesystem path,
resolves symlinks, invokes a command, obtains a network resource, or owns a file
descriptor. The later retained I/O session owns acquisition, origin validation,
disjointness, descriptor lifetime, stamps, complete sets and final verification.
One command uses one fresh compiled context from its one retained graph.

## Private interfaces

`resource_origin_plan()` takes no arguments. It returns an immutable
`ResourceOriginPlan` with `layout`, `package_directory`, `schemas_directory`,
`profiles_directory` and `resources`. Directory values are absolute lexical
strings. Resources is an ASCII-sorted tuple of immutable `ResourcePin` records
with `relative_path`, `size_bytes`, and `sha256`. Logical paths are the ten
`schemas/<filename>` names and `profiles/code-proof-v1.json`.

The plan is tied to this imported module's absolute `__file__`, with the module
directly under `video_paper_wiki`. If that package's direct parent is named
`src`, layout is source and schema origin is its parent's `schemas` directory.
Otherwise layout is installed and schema origin is package `schemas`.
Profiles always comes from package `profiles`. This lexical classification is
fixed for the imported module; it does not probe an alternative or use CWD,
environment variables, caller paths, resource existence, a global cache, or
`Path.resolve`. Reject relative, NUL-containing or dot/dot-dot-component module
origins. A filesystem-backed directory and no-follow lineage are established
later by I/O; an archive-style origin cannot acquire authority from this plan.
The source-layout naming rule is explicit: an installed package placed directly
under a directory literally named `src` selects the source plan and must satisfy
that plan, without an existence-based fallback.

`compile_code_proof_resources(retained_bytes)` takes an exact builtin dict whose
keys are exact builtin strings and whose values are exact builtin bytes. It
requires exactly the eleven logical paths above, with no extra keys. It returns
one fresh `CodeProofResources`. No pin, profile, origin, validator, registry,
callback, or dependency path can be supplied by the caller.

`CodeProofResources.profile_sha256` is the pinned profile digest.
`CodeProofResources.resource_pins` is the immutable pin tuple. The object exposes
no parsed schema/profile, mutable resource map, validator, registry or descriptor.
Retained bytes and parsed validation structures are owned privately; subsequent
mutation of the caller's input dict cannot affect the context. Do not use a
process-global compiled-resource/validator cache.

`CodeProofResources.validate_structure(title, instance)` validates a complete
object under one exact declared title and returns `None`. It never returns the
input or a claim of accepted evidence. Titles are the ten inventory titles; the
common title is permitted for its declared root schema, with profile validation
handled separately during compilation. No arbitrary URI, filename or fragment
selector is accepted. Check exact builtin title type and inventory membership.

Before schema validation, iteratively reject non-JSON Python objects, subclasses
of dict/list/str/int/float, non-string object keys, floats (including 1.0),
nonfinite values, surrogate codepoints in keys or strings, and container cycles.
Permit only exact dict/list/str/int/bool and None; check bool distinctly from
integer. Shared acyclic values are permitted. Do not mutate or normalize values.
The validator uses an explicit strict integer type checker (`type(value) is int`).
This interface validates structural shape only. All ce1/JCS/LF identity checks,
metadata NFC, semantic string byte bounds, ordering, request lowering/binding,
raw hashes, state and derived replay remain at the later public boundary.
In particular, source text and decoded configuration values retain their Unicode
spelling, and resealing a fabricated derivation does not make it accepted.

`CodeProofResources.materialize_limits(value)` accepts None for the installed
full limits or an exact complete builtin three-group map. With a map, every
group/key must match the installed `limits`, and each value must be an exact
positive int no greater than its pinned hard maximum. Return a new independent
plain dict with independent nested dicts. None means the caller omitted optional
limits; the public ordinary-input schema must reject an explicit JSON null
before this helper is used. Fixed `admission` caps never enter this operation.

## Compile order and trust root

Production constants pin all eleven exact reviewed sizes and SHA-256 digests.
They come from the accepted external resource manifest, never from caller input
or solely from the profile's internal inventory. Validate the complete input
mapping, then compare lengths and hashes in ASCII logical-path order before any
JSON parse or validator construction. A self-consistent replacement set refuses.

Parse exact retained bytes as UTF-8 without BOM, duplicate keys, float or
nonfinite numbers, surrogate strings or trailing JSON. Require the exact R12
resource formatting: two-space JSON indentation, ensure_ascii=False, and one
terminal LF, with the resource's parsed key order preserved when checking bytes.
The pinned byte check is not replaced by normalization. The resource parser is
private to compilation; it is not a public document/JSON parser. No new metadata
integer-range or depth limit is inferred from the JCS implementation here.

Verify each schema's Draft 2020-12 dialect, exact filename/title/$id identity,
Draft schema validity, and R12 reference closure. Walk schema nodes to reject
nested `$id`, `$dynamicRef`, `$dynamicAnchor`, `$anchor` and recursive-reference
extensions. Every `$ref` must be a same-document fragment or one exact declared
absolute schema ID with an optional fragment. Empty fragment names the root;
nonempty fragments must be JSON Pointers. Decode valid ~0/~1 escapes and require
each pointer to resolve in that document; reject malformed escapes, URI escape
aliases, relative or undeclared references. No registry or resolver may retrieve
anything outside these ten resources, including the Draft dialect URI.

Create a fresh explicit `referencing.Registry` containing exactly those ten
schema resources and a retrieval function that always refuses. There is no
eleventh schema/profile registration. Validate the complete parsed profile via
the common schema's exact `/$defs/profile` definition and that same registry.
Check its ten sorted unique inventory rows against the production pins and all
R12 exact profile fields, hard maxima and fixed admission caps. Keep every
validator bound to this context's exact retained schema bytes.

## Private errors and later public mapping

`CodeProofResourceError` exposes only `reason`, one of `resource_origin`,
`resource_hash` or `resource_shape`, plus a fixed safe message. Origin-plan
validation uses resource_origin; byte size/hash mismatch uses resource_hash;
mapping/type/parse/Draft/profile/reference failures use resource_shape.

`CodeProofStructureError` exposes only `reason`, one of `type`, `shape` or
`limits`, plus a fixed safe message. Exact-type/cycle/surrogate rejection uses
type; title/structural-validator rejection uses shape; the limit helper uses
limits. Exceptions do not contain raw paths, arbitrary keys/values, parser text,
resolver text or validator diagnostics. Suppress chained raw exception output
at this boundary. These are private errors, not a new public error envelope.

The later I/O boundary maps initial resource failures into the complete R8
nine-field CODE_PROOF_RESOURCE_INVALID context, preserving contracted initial
missing/type reasons during acquisition. A later retained-lineage failure still
wins as WORK_PATH_UNSAFE, including on parse, validation and cleanup exits.
The public layer maps structure errors into its existing bounded error context
only after its own strict parser and semantic preflight.

## Acceptance

Tests load the actual eleven frozen resources as test inputs and compile fresh
contexts. Replay the existing 264 structural fixture cases without modifying
that fixture. Exercise independent contexts, pin mutations, missing/extra/non-
builtin mapping entries, self-consistent resource/profile replacement, refused
reference forms/targets, strict parser negatives, exact types/subclasses/cycles,
surrogates, acyclic sharing, unknown titles and every limit key's 1/max/max+1,
zero/bool/float/missing/extra boundaries. Private reference/parser helpers may be
tested on mutated structures separately because production pin refusal precedes
their invocation. Do not weaken pins merely to reach those helpers in a test.

Prove no filesystem/network/subprocess/legacy-loader activity during import,
origin planning, compilation and validation, apart from Python's normal module
import mechanism in an independently imported test setup. Assert fixed error
content with adversarial marker values. Test source and installed origin plans,
changed CWD independence and absence of origin fallback. Installed-wheel checks
must import the actual module from a fresh installation and use its real package
resources; a mocked path-only test does not establish wheel parity.

Grok is given self-contained natural-language implementation instructions with
literal interface names and necessary constants, without repository attachments
or file/shell/model tools. It returns the two complete source blocks for local
review. Any follow-up correction remains a fresh bounded instruction. Run focused
checks, both locked full suites and an installed wheel after the Builder stops.
The foundation cannot close the public CODE item, real-source verification,
remote CI or human semantic gates.
