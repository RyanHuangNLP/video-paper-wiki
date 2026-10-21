# CODE proof identity and layout — R4 candidate

Architect design, pending independent review and a complete public-wire freeze.
No Builder implementation dispatch is authorized. This supplements unchanged
CODE-PROOF-DESIGN-R2 and CODE-PROOF-CLOSURE-R3, closing saved identity, concrete
layout and byte-budget decisions. Exact public request/observation/config/handoff
data schemas and retained-I/O implementation review remain separate work.
The current source implementation scope is still the frozen three-file Git
kernel; its denied external retry must not be inferred authorized from this file.

## Complete document identity

Exactly six saved envelope kinds belong to this CODE-PROOF generation:
code-proof-request, code-git-bundle, code-acquisition-intent,
code-proof-observation, code-config-evidence, code-source-handoff.

Each envelope is the closed object `{schema, kind, id, data}`. `kind` is one of
those exact strings; `schema` is `video-paper-wiki.<kind>.v1`. Define:

```text
core = {schema, kind, data}
digest = lowercase_hex(SHA256(video_paper_wiki.jcs.canonicalize(core)))
id = "ce1:" + kind + ":" + digest
saved = video_paper_wiki.jcs.canonicalize({schema, kind, id, data}) + LF
reference = {id, sha256: lowercase_hex(SHA256(saved))}
```

The ID hashes canonical core bytes without LF; the reference hashes complete
saved envelope bytes including exactly one terminal LF. No content_sha256 field,
timestamp exclusion, path exclusion, deleted field or circular self-reference.
The schema and kind separate domains, so identical data under different kinds
has different identity. No discovery rw3 envelope or source-association digest
is interchangeable with this ce1 reference.

Before any identity calculation validate strict primitive shapes, integer-only
numbers, string bounds, no surrogates and closed fields. Metadata identity strings
must already be NFC. The exact exceptions are retained normalized-text content,
configuration decoded values/keys, their derived JSON Pointers and original
numeric lexemes: these preserve source spelling. They are not NFC-transformed
merely because the envelope is canonical JSON. JCS object keys follow the
existing UTF-16 order; explicit data-array ordering remains each contract's
specified order (for example UTF-8 logical paths and config node preorder).

Saved files must equal the byte-exact canonical encoding above. Reject BOM,
duplicate keys, noncanonical spacing/number/escape encodings, multiple terminal
LFs, trailing bytes, wrong ID and wrong referenced saved-byte hash. External
ordinary request/observe input files are strict JSON under their own closed
input schemas; they are not required to be presealed envelopes. A raw bundle's
manifest.json is explicitly a saved code-git-bundle envelope and is canonical.

At no point is the supplied bundle directory's unrelated lexical contents hash
a substitute for the manifest's complete saved-byte reference. An intent binds
that reference, the raw input directory's canonical checkout-relative spelling,
request reference, mode and the entire supplied normalized acquisition metadata.
Thus all declared raw object identities are transitively bound by the intent.
There is no direct intent -> observation reference or other identity cycle.

The source-association reference is the existing closed
`{association_id: "sva-" + 64lowerhex, sha256: 64lowerhex}`. Its sha256 is the
source_semantics_contracts.association_reference digest of that legacy canonical
document, without an invented saved-LF conversion. The request preserves that
unverified external reference; CODE-PROOF never asserts it resolves or owns a
source. Its eventual canonical successor must verify exact association semantics.

## Fixed output layout and names

The namespace is checkout-relative `.work/<batch>/code-evidence-v1/`, where
batch uses the existing approved batch identifier grammar. There are exactly
four possible direct file slots and three possible direct directory slots:

| slot/family | maximum bytes per file | maximum files |
| --- | ---: | ---: |
| request.json | 65536 | 1 |
| intent.json | 1048576 | 1 |
| bundle.json | 1048576 | 1 |
| observation.json | 2097152 | 1 |
| objects/<oid>.body | 8388608 | 2048 |
| configs/<path-key>.json | 2097152 | 32 |
| handoffs/<path-key>.json | 131072 | 32 |

This is a seven-slot layout with bounded families, not a literal twelve-path
allowlist. All limits count full saved bytes or raw body bytes as appropriate.
Object-format width in each object basename is exactly 40 or 64 lowercase hex
from the request; suffix is exactly `.body`. An object filename never supplies
its type or raw-body digest; those come from the validated bundle inventory.

path-key is lowercase hex of SHA256(logical_target_path.encode('ascii')),
exactly 64 characters; suffix is `.json`. It is only a deterministic filename
key, not a replacement for envelope ID or source evidence identity. Every file
must carry its exact original requested path inside its validated data. Before
installing config/handoff outputs, require generated filenames to be unique;
an unexpected name collision is refused rather than overwriting another path.
This permits long/deep Git paths without recreating their source directory tree.

No nested family directory, unknown direct sibling, alternate suffix, alias,
symlink, hardlink, FIFO, socket or special file is permitted. Output files are
single-link regular files with exact mode 0600; generated directories exact
0700. The checkout/.work/batch ancestor policies remain their existing retained
authority rules and are not silently chmodded by this new module.

request may exist alone. Families are created lazily when first needed, and
absent versus initially empty known directories is tracked in initial snapshots.
An empty known family may remain after interrupted creation; status may report
it as pending but must not invent an artifact. Normalized-only completed batches
forbid bundle.json, objects/, configs/ and handoffs/ even when those directories
are empty. A git_objects batch may use the named families only for its exact
replayed dependencies and deterministic derivations. Root directories retain
complete scoped entry snapshots before any unsafe/unknown entry classification.

The input raw bundle has exactly manifest.json and objects/, with no other
entry. Its manifest shares the 1 MiB complete saved-byte cap. objects/ contains
exactly the declared OID bodies, with no directories. Input files are single-link
regular files and must not have executable or group/other write bits. Input
directory paths must be nonsymlink retained directories; their identities and
modes must remain unchanged through all exits. No input chmod/repair is allowed.
Input/output disjointness and canonical .work spelling follow R3; reject equal
or ancestor descriptor/path lineages before any output creation.

## Resource and derived-file bindings

The complete public wire freeze will supply one installed code-proof profile
and all new schema byte hashes as an exact resource set. The request carries
profile_sha256. Every command retains those actual files and a fresh registry
with its other inputs; none may silently use a different default cached registry.
The code-config-kernel profile is materialized inside that installed profile,
alongside the Git kernel and public caps. The complete request limits map may
lower positive maxima but cannot raise or omit their materialized saved values.

bundle.json in output is byte-identical to the supplied canonical manifest.json.
The raw intent and observation retain its saved-byte reference; all objects are
bound by its exact ordered inventory. Config and handoff files bind their
request/observation/bundle refs, path, raw blob OID and raw-body reference. A raw
body reference has exactly `{path, size_bytes, sha256}`, where path is the
checkout-relative canonical stored objects/<oid>.body spelling, size is exact
raw bytes and sha256 is body_sha256, not framed_sha256 or a Git OID.

Config/handoff bytes are accepted only when byte-identical to fresh pure
derivation from the complete retained observation and objects under the same
profile. Re-sealing a forged result with a correct ce1 ID does not validate it.
One config result per requested path is immutable. Repeating identical format
and bytes reuses it; requesting a different json/toml/source-only derivation for
that path conflicts and requires a new batch. The explicit source-only branch
stores null parsed result and a closed reason, and never forges typed nodes.

Handoffs contain successor_only=true and no legacy-capture eligibility field.
They keep object_format and full-width commit/root-tree/blob OIDs. A phase-1
command never passes them into legacy 40-hex capture/preparation adapters.
The later public-wire schema will close every remaining handoff data field and
ensure the 128 KiB cap before writing. This file does not declare that schema
finished merely by naming the required bindings.

## Byte budgets and interruption

The maximum aggregate raw object body size is 33554432 bytes. The output peak
budget is 134217728 bytes. Both are logical byte counts, not disk block usage,
directory st_size, compressed size or process resident memory. Byte counts are
strict nonnegative integers. All positive request/profile limits are strict
integers and may be lowered within their permitted maxima.

For retained existing regular files, charge their actual stat size before reading
and verify it against the retained actual bytes. Charge every observed entry's
known regular-file size even if pending, orphaned or later refused. An unknown
or per-file oversized entry refuses before reading its contents; do not produce
an accepted budget by ignoring it. Directories contribute zero logical file
bytes but must satisfy bounded entry-count and complete-set rules. Unsafe types
are refused, not treated as free reusable files.

Pre-serialize every generated document under its per-file cap. An absent-target
install of payload length N is authorized only if current_retained_file_bytes
+ N <= max_output_peak_bytes. One exclusive single-link private temp contains
at most N bytes, and the installer atomically renames that same inode to the
previously absent final slot; it does not keep an additional copy of N after
rename. The prospective-final and temp phases each charge the same N once,
not twice. Existing identical targets are retained/reused without creating a
temp. No replacement/overwrite of an existing target is allowed.

If the chosen concrete installer duplicates an existing target, creates more
than one simultaneous temp, or writes an additional full copy before rename,
this accounting proof is invalid: that installer must be changed or a reviewed
budget amendment must account for the actual simultaneous bytes. A guessed
"8 MiB reserve" must not replace inspection of the concrete write path.

Private temp names use an implementation-private bounded basename and are valid
only while owned by the current retained command. Capture their returned inode
and original named edge, verify mode/link count/bytes and remove the owned temp
on every exceptional exit. Do not remove an unrelated replacement or claim its
name was absent without checking it. A leftover temp discovered on a later
command is an unknown entry and refuses; it is never promoted to a final artifact.

Observe install order is request (already present), intent, bundle, OID-sorted
bodies, observation last. Fully preflight the external input before the first
new intent write. Repair requires the same originally bound external input path,
manifest, body inventory and normalized acquisition metadata and revalidates
them before writes. Status never repairs. Config/handoff replay only completed
stored data and never reopens the external raw input path.

An intent without observation is pending. After retaining its canonical bundle,
status computes exact expected body names and reports any missing dependencies
or final observation. Before bundle is installed, status knows intent's bound
manifest reference but cannot invent its not-yet-retained object inventory; it
reports that bundle is needed. A completed observation with a missing dependency
is corrupt. A matching observed prefix is reusable only if present at the initial
scan; late insertion after captured absence is unsafe even when bytes match.

On all successes and refusals revalidate every retained named edge and complete
scoped directory snapshot against authorized installs/cleanup. Persistent
lineage failure overrides an earlier semantic error. The detailed retained-I/O
freeze must identify the concrete retained session and atomic installer and
cover no-request, parse failure, oversized input, interrupted install, conflict,
unexpected sibling and cleanup races before public implementation dispatch.
